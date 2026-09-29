"""Local v1 workbench: bounded replay, immutable media, same-origin task controls."""
import base64
import html
import json
import mimetypes
import os
import re
import secrets
import socketserver
import threading
import time
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from pydantic import ValidationError

from .dashboard_control import ControlConflict, WebotsController

ASSETS = Path(__file__).with_name('dashboard')
DOWNLOADS = {'trace.jsonl','summary.json','configuration.json','launch.json','evaluation.json',
             'actions.csv','api-metrics.csv','api-metrics.jsonl','report.html','agent-photo-reviews.json'}
MAX_EVENTS = 10000
PAGE_SIZE = 250


def _json_file(path, default=None):
    try:
        return default if path.is_symlink() else json.loads(path.read_text())
    except (OSError,ValueError):
        return default


def media_url(run, path):
    return '/media/'+quote(run,safe='')+'/'+quote(path,safe='/')


def _image(run, record):
    return dict(record,image_url=media_url(run,record['path'])) if record and record.get('path') else record


class RunReader:
    def __init__(self, directory, name):
        self.directory,self.name = directory,name
        self.reset()

    def reset(self):
        self.offset = 0
        self.inode = None
        self.first_time = None
        self.sequence = 0
        self.prefix = self.tail = b''
        self.events = deque(maxlen=MAX_EVENTS)
        self.state = {'observation':None,'pending_inference':None,'pending_action':None,
                      'review_checkpoint':None,'last_tool':None,'elapsed_s':0.,'photo_frame':None,
                      'pending_reference':None}

    def read(self):
        path = self.directory/'trace.jsonl'
        if path.is_symlink():
            self.reset(); return True
        try:
            stat = path.stat()
        except OSError:
            return False
        replaced = self.inode is not None and (stat.st_ino != self.inode or stat.st_size < self.offset)
        with path.open('rb') as stream:
            if self.offset and not replaced:
                prefix = stream.read(len(self.prefix))
                stream.seek(self.offset-len(self.tail))
                replaced = prefix != self.prefix or stream.read(len(self.tail)) != self.tail
            if replaced:
                self.reset()
            self.inode = stat.st_ino
            stream.seek(self.offset)
            for _ in range(2000):
                line = stream.readline(2*1024*1024)
                if not line.endswith(b'\n'):
                    break
                self.offset = stream.tell()
                try:
                    row = json.loads(line)
                except (ValueError,UnicodeError):
                    continue
                if not isinstance(row,dict) or not isinstance(row.get('data'),dict) or not isinstance(row.get('wall_time'),(int,float)):
                    continue
                timestamp = row['wall_time']
                if self.first_time is None:
                    self.first_time = timestamp
                self.sequence += 1
                row.update(id=self.sequence,elapsed_s=max(0.,timestamp-self.first_time))
                kind,data = row.get('event'),row['data']
                if kind == 'observation':
                    data['image'] = _image(self.name,data.get('image'))
                    self.state['observation'] = data
                elif kind in ('capture','crop','frame_preview','viewfinder','reference'):
                    row['data'] = _image(self.name,data)
                elif kind=='reference_started':
                    self.state['pending_reference']=dict(data,wall_time=timestamp)
                elif kind=='reference_attempt':
                    self.state['pending_reference']=None
                elif kind == 'inference_started':
                    self.state['pending_inference'] = dict(data,wall_time=timestamp)
                elif kind == 'inference_finished':
                    self.state['pending_inference'] = None
                elif kind == 'decision':
                    self.state['last_tool'] = data.get('tool')
                    self.state['pending_inference'] = None
                elif kind == 'action_started':
                    self.state['pending_action'] = dict(data,wall_time=timestamp)
                elif kind in ('action_result','landing'):
                    self.state['pending_action'] = None
                elif kind == 'photo_frame':
                    self.state['photo_frame'] = data
                elif kind == 'review_checkpoint':
                    self.state['review_checkpoint'] = data if data.get('status') == 'required' else None
                self.state['elapsed_s'] = row['elapsed_s']
                self.events.append(row)
            stream.seek(0)
            self.prefix = stream.read(min(256,self.offset))
            stream.seek(max(0,self.offset-256))
            self.tail = stream.read(min(256,self.offset))
        return replaced


class RunStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.readers = OrderedDict()
        self.lock = threading.Lock()

    def run_path(self, name):
        parts = name.split('/')
        if any(not part or part in ('.','..') or '\\' in part for part in parts):
            raise FileNotFoundError(name)
        path = self.directory
        for part in parts:
            path /= part
            if path.is_symlink():
                raise FileNotFoundError(name)
        if not path.is_dir() or self.directory not in path.resolve().parents:
            raise FileNotFoundError(name)
        return path

    def file_path(self, run, relative):
        parts = relative.split('/')
        if relative not in DOWNLOADS and not (len(parts)==2 and parts[0] in ('frames','shots','crops','previews','live','references')
                                                and Path(parts[1]).suffix.lower() in ('.png','.jpg')):
            raise FileNotFoundError(relative)
        path = self.run_path(run)
        for part in parts:
            if part in ('','.','..') or '\\' in part:
                raise FileNotFoundError(relative)
            path /= part
            if path.is_symlink():
                raise FileNotFoundError(relative)
        if not path.is_file():
            raise FileNotFoundError(relative)
        return path

    def _info(self, path):
        config = _json_file(path/'configuration.json',_json_file(path/'launch.json',{}))
        summary = _json_file(path/'summary.json')
        updated = max((p.stat().st_mtime for p in (path/'trace.jsonl',path/'preview.json',path/'launch.json')
                       if p.is_file() and not p.is_symlink()),default=path.stat().st_mtime)
        return {'id':path.relative_to(self.directory).as_posix(),'brief':config.get('brief',''),
                'scenario':config.get('scenario'),'model':config.get('model',''),
                'status':summary.get('status','finished') if summary else ('active' if time.time()-updated<15 else 'inactive'),
                'updated_at':updated,'has_summary':summary is not None}

    def report(self, name):
        report = self.file_path(name,'report.html').read_text()
        def embed(match):
            relative = html.unescape(match.group(1))
            if relative.split('/')[0] not in ('shots','crops','frames','previews','references'):
                raise FileNotFoundError(relative)
            path = self.file_path(name,relative)
            mime = mimetypes.guess_type(path.name)[0]
            return '<img src="data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()+'">'
        return re.sub(r'<img src="([^"]+)">',embed,report).encode()

    def list_runs(self):
        paths = []
        for parent,children,files in os.walk(self.directory):
            path = Path(parent)
            if path != self.directory and any(name in files and not (path/name).is_symlink() for name in ('trace.jsonl','launch.json')):
                paths.append(path); children[:] = []
            else:
                children[:] = [name for name in children if not name.startswith('.') and not (path/name).is_symlink()]
        return sorted((self._info(p) for p in paths),key=lambda r:r['updated_at'],reverse=True)

    def preview(self, name):
        data = _json_file(self.run_path(name)/'preview.json')
        if data:
            data['image_url'] = media_url(name,data['image_path'])
            data['photo_image_url'] = media_url(name,data['photo_path']) if data.get('photo_path') else None
            data['viewfinder_image_url'] = media_url(name,data['viewfinder_path']) if data.get('viewfinder_path') else None
        return data

    def snapshot(self, name, after):
        directory = self.run_path(name)
        with self.lock:
            reader = self.readers.get(name)
            if reader is None:
                reader = self.readers[name] = RunReader(directory,name)
            self.readers.move_to_end(name)
            while len(self.readers)>8:
                self.readers.popitem(last=False)
            reset = reader.read()
            first_id = reader.events[0]['id'] if reader.events else 1
            reset = reset or after>reader.sequence or after!=0 and after<first_id-1
            after = 0 if reset else after
            events = [row for row in reader.events if row['id']>after][:PAGE_SIZE]
            cursor = events[-1]['id'] if events else after
            images = _json_file(directory/'images.json',{})
            summary = _json_file(directory/'summary.json')
            state = dict(reader.state,started_at=reader.first_time,configuration=_json_file(directory/'configuration.json',_json_file(directory/'launch.json',{})),
                         summary=summary,photos=[_image(name,p) for p in images.values() if p.get('kind') in ('capture','crop')],
                         references=[_image(name,p) for p in images.values() if p.get('kind')=='reference'],
                         reviews=_json_file(directory/'agent-photo-reviews.json',[]),
                         evaluation=_json_file(directory/'evaluation.json'),provider=_json_file(directory/'provider.json'))
            if summary:
                state['pending_inference'] = state['pending_action'] = state['pending_reference'] = None
            return {'run':self._info(directory),'state':state,'events':events,'next_cursor':cursor,
                    'more':cursor<reader.sequence,'reset':bool(reset),'preview':self.preview(name),'server_time':time.time(),
                    'downloads':{name:media_url(reader.name,name) for name in sorted(DOWNLOADS) if (directory/name).is_file() and not (directory/name).is_symlink()}}


def make_server(directory, port=8766, env_file=None, controller=None):
    store = RunStore(directory)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def local(self):
            return self.headers.get_all('Host',[]) in ([f'127.0.0.1:{self.server.server_port}'],[f'localhost:{self.server.server_port}'])

        def send(self, body, mime, status=200, download=None):
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if download:
                self.send_header('Content-Disposition',f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def json(self, value, status=200):
            self.send(json.dumps(value,ensure_ascii=False).encode(),'application/json; charset=utf-8',status)

        def do_GET(self):
            if not self.local():
                self.json({'error':'localhost only'},403); return
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == '/api/control':
                    self.json(dict(self.server.controller.snapshot(),token=token))
                elif url.path == '/api/runs':
                    self.json(store.list_runs())
                elif url.path == '/api/snapshot':
                    self.json(store.snapshot(query.get('run',[''])[0],max(0,int(query.get('after',['0'])[0]))))
                elif url.path == '/api/preview':
                    self.json(store.preview(query.get('run',[''])[0]))
                elif url.path == '/' or url.path.startswith('/assets/'):
                    asset = 'index.html' if url.path == '/' else url.path.removeprefix('/assets/')
                    if asset not in ('index.html','dashboard.css','dashboard.js'):
                        raise FileNotFoundError(asset)
                    self.send((ASSETS/asset).read_bytes(),mimetypes.guess_type(asset)[0] or 'application/octet-stream')
                elif url.path.startswith('/media/'):
                    _,_,run,*parts = url.path.split('/')
                    path = store.file_path(unquote(run),'/'.join(unquote(p) for p in parts))
                    body = store.report(unquote(run)) if path.name=='report.html' else path.read_bytes()
                    self.send(body,mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                              download=path.name if path.name in DOWNLOADS else None)
                else:
                    raise FileNotFoundError(url.path)
            except (FileNotFoundError,KeyError):
                self.json({'error':'not found'},404)
            except (ValueError,TypeError):
                self.json({'error':'invalid request'},400)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def do_POST(self):
            origins = self.headers.get_all('Origin',[])
            tokens = self.headers.get_all('X-Drone-Control-Token',[])
            if not self.local() or origins != ['http://'+self.headers.get('Host','')] or len(tokens)!=1 or not secrets.compare_digest(tokens[0].encode(),token.encode()):
                self.json({'error':'控制请求必须来自当前本地面板。'},403); return
            action = urlsplit(self.path).path
            if action not in ('/api/control/start','/api/control/stop'):
                self.json({'error':'method unavailable'},405); return
            try:
                lengths = self.headers.get_all('Content-Length',[])
                if self.headers.get_content_type()!='application/json' or self.headers.get('Transfer-Encoding') or len(lengths)!=1:
                    raise ValueError('需要 JSON 和明确的内容长度。')
                length = int(lengths[0])
                if not 0<length<=8192:
                    raise ValueError('请求长度超限。')
                self.connection.settimeout(3)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload,dict):
                    raise ValueError('需要 JSON 对象。')
                if action.endswith('/start'):
                    state = self.server.controller.start(payload)
                else:
                    if payload:
                        raise ValueError('停止操作不接受附加参数。')
                    state = self.server.controller.stop()
                self.json(dict(state,token=token),202)
            except ControlConflict as error:
                self.json({'error':str(error)},409)
            except ValidationError:
                self.json({'error':'任务参数无效，请检查场景、模型、时长和任务文本。'},400)
            except (ValueError,UnicodeError) as error:
                self.json({'error':str(error)},400)
            except OSError:
                self.json({'error':'本地控制操作失败，请检查 Webots 与运行目录。'},500)

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        def server_bind(self):
            socketserver.TCPServer.server_bind(self)
            self.server_name,self.server_port = self.server_address[:2]

        def server_close(self):
            super().server_close()
            if hasattr(self,'controller'):
                self.controller.close()

    server = Server(('127.0.0.1',port),Handler)
    server.controller = controller or WebotsController(directory,env_file)
    return server


def serve(directory, port=8766, env_file=None, open_browser=False):
    import webbrowser
    server = make_server(directory,port,env_file)
    url = f'http://127.0.0.1:{server.server_port}'
    print('v1 workbench: '+url,flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
