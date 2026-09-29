"""Explicit local Webots lifecycle and provider selection, isolated from agent policy."""
import fcntl
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from .artifacts import write_json
from .cli import ROOT, WEBOTS
from .protocol import StrictModel
from .reference import reference_environment


class ControlConflict(RuntimeError):
    pass


class StartRequest(StrictModel):
    brief: Annotated[str, Field(min_length=1, max_length=2000, pattern=r'\S')]
    scenario: Literal['facing','open','hidden','terrace'] = 'terrace'
    provider: Literal['openlux','alicloud','environment','scripted'] = 'openlux'
    model: Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$')] = 'gemini-3.6-flash'
    duration_s: Annotated[int, Field(ge=30, le=1800)] = 900
    navigation_history: bool = True
    reference_generation: bool = True


def _credentials(path):
    values = {}
    if path and Path(path).is_file():
        for line in Path(path).read_text().splitlines():
            line = line.strip().removeprefix('export ')
            if not line or line.startswith('#') or '=' not in line:
                continue
            key,value = line.split('=',1)
            if key.strip() in ('BASE_URL','API_KEY','AliCloud_url','AliCloud_key',
                               'DRONE_PHOTO_VLM_BASE_URL','DRONE_PHOTO_VLM_API_KEY',
                               'DRONE_PHOTO_IMAGE_BASE_URL','DRONE_PHOTO_IMAGE_API_KEY'):
                values[key.strip()] = ' '.join(shlex.split(value,comments=True))
    return values


def provider_environment(provider, env_file=None):
    values = _credentials(env_file)
    keys = {'openlux':('BASE_URL','API_KEY'),'alicloud':('AliCloud_url','AliCloud_key'),
            'environment':('DRONE_PHOTO_VLM_BASE_URL','DRONE_PHOTO_VLM_API_KEY')}
    url_key,key_key = keys[provider]
    source = dict(os.environ) | values if provider == 'environment' else values
    url,key = source.get(url_key),source.get(key_key)
    if not url or not key:
        raise ValueError('所选接口未配置完整的地址和凭据。')
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('接口地址必须是无凭据、无查询参数的 HTTP(S) URL。')
    return {'DRONE_PHOTO_VLM_BASE_URL':url,'DRONE_PHOTO_VLM_API_KEY':key}


def provider_options(env_file=None):
    result = []
    for identity,label,model in [('openlux','OpenLux','gemini-3.6-flash'),
                                 ('alicloud','阿里云官方','qwen3.8-flash'),
                                 ('environment','自定义环境变量','gemini-3.6-flash')]:
        try:
            env = provider_environment(identity,env_file)
            endpoint,ready = env['DRONE_PHOTO_VLM_BASE_URL'],True
        except ValueError:
            endpoint,ready = None,False
        result.append({'id':identity,'label':label,'default_model':model,'ready':ready,'endpoint':endpoint})
    result.append({'id':'scripted','label':'工程检查（无 API）','default_model':'scripted','ready':True,'endpoint':None})
    return result


class WebotsController:
    def __init__(self, directory, env_file=None, webots=WEBOTS):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True,exist_ok=True)
        self.env_file = env_file
        self.webots = Path(webots)
        self.lock = threading.RLock()
        self.process = None
        self.file_lock = None
        self.log = None
        self.run = None
        self.state = 'idle'
        self.error = None
        self.stop_requested = False
        self.closed = False
        self.monitor = None

    def snapshot(self):
        with self.lock:
            return {'state':self.state,'active_run':self.run,
                    'busy':self.process is not None and self.process.poll() is None,
                    'error':self.error,'providers':provider_options(self.env_file),
                    'webots_available':self.webots.is_file()}

    def start(self, payload):
        request = StartRequest.model_validate(payload)
        with self.lock:
            if self.closed or self.monitor is not None and self.monitor.is_alive():
                raise ControlConflict('已有 Webots 任务正在运行或收尾。')
            if not self.webots.is_file():
                raise ValueError('未找到 Webots 可执行文件。')
            credentials = {} if request.provider == 'scripted' else provider_environment(request.provider,self.env_file)
            if request.provider != 'scripted' and request.reference_generation:
                credentials.update(reference_environment(dict(os.environ)|_credentials(self.env_file)))
            control = self.directory/'.dashboard'
            control.mkdir(exist_ok=True)
            lease = (control/'webots.lock').open('a')
            try:
                fcntl.flock(lease,fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lease.close()
                raise ControlConflict('另一个工作台仍持有 Webots 任务，请等待其结束。') from None
            identity = 'dashboard-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            run = self.directory/identity
            command = [sys.executable,'-m','drone_agent','run','--scenario',request.scenario,
                       '--brief',request.brief,'--model',request.model,'--duration',str(request.duration_s),
                       '--output',str(run),'--webots',str(self.webots)]
            if not request.navigation_history:
                command.append('--no-history')
            if not request.reference_generation or request.provider=='scripted':command.append('--no-reference')
            if request.provider == 'scripted':
                script = control/'engineering-flight.json'
                write_json(script,[{'tool':'act','arguments':{'kind':'takeoff'}},
                    {'tool':'act','arguments':{'kind':'hold','value':30}},
                    {'tool':'act','arguments':{'kind':'land'}},
                    {'tool':'finish','arguments':{'shot_id':None,'abandon':True}}])
                command.extend(['--script',str(script)])
            env = dict(os.environ,PYTHONPATH=str(ROOT/'src'),PYTHONUNBUFFERED='1')
            for key in ('DRONE_PHOTO_VLM_API_KEY','DRONE_PHOTO_VLM_BASE_URL','DRONE_AGENT_SCRIPT','DRONE_AGENT_BASELINE',
                        'DRONE_PHOTO_IMAGE_BASE_URL','DRONE_PHOTO_IMAGE_API_KEY','BASE_URL','API_KEY'):
                env.pop(key,None)
            env.update(credentials)
            log = (control/(identity+'.log')).open('w')
            try:
                process = subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                                           start_new_session=True,pass_fds=(lease.fileno(),))
            except BaseException:
                lease.close(); log.close()
                raise
            self.process,self.file_lock,self.log = process,lease,log
            self.run,self.state,self.error,self.stop_requested = identity,'starting',None,False
            self.monitor = threading.Thread(target=self._watch,args=(process,run,request.provider,credentials.get('DRONE_PHOTO_VLM_BASE_URL')),
                                            name='webots-task',daemon=True)
            self.monitor.start()
            return self.snapshot()

    def _watch(self, process, run, provider, endpoint):
        published = False
        while process.poll() is None:
            with self.lock:
                if run.is_dir():
                    if not published:
                        write_json(run/'provider.json',{'provider':provider,'endpoint':endpoint})
                        published = True
                    if self.stop_requested:
                        (run/'stop.request').touch()
                    elif (run/'trace.jsonl').exists():
                        self.state = 'running'
            time.sleep(.1)
        with self.lock:
            self.state = 'finished' if (run/'summary.json').exists() else 'failed'
            self.error = None if self.state == 'finished' else '启动器未生成结果；请检查本机 .dashboard 运行日志。'
            self.file_lock.close(); self.log.close()
            self.file_lock = self.log = None

    def stop(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.stop_requested = True
                self.state = 'stopping'
                run = self.directory/self.run
                if run.is_dir():
                    (run/'stop.request').touch()
            return self.snapshot()

    def close(self):
        with self.lock:
            self.closed = True
            self.stop()
        if self.monitor:
            self.monitor.join(timeout=60)
        return self.process is None or self.process.poll() is not None
