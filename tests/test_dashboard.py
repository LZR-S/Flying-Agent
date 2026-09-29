"""Workbench boundaries: immutable evidence, local control, and public live frames."""
import json
import threading
import time
from http.client import HTTPConnection

import cv2
import numpy as np
import pytest

from drone_agent.artifacts import Artifacts, write_json
from drone_agent.protocol import Config
from test_protocol_context import obs


def test_incremental_trace_partial_lines_and_replacement(tmp_path):
    from drone_agent.dashboard import RunStore
    a = Artifacts(tmp_path/'one', Config())
    a.observe(obs(1))
    store = RunStore(tmp_path)
    first = store.snapshot('one', 0)
    assert first['events'][0]['data']['image']['image_url'].endswith('/frames/frame_000001.png')
    cursor = first['next_cursor']
    with a.trace.open('a') as f:
        f.write('{"event":"decision","wall_time":100,"data":')
    assert store.snapshot('one', cursor)['events'] == []
    with a.trace.open('a') as f:
        f.write('{"tool":"capture"}}\n')
    assert store.snapshot('one', cursor)['events'][0]['data']['tool'] == 'capture'
    a.trace.write_text('{"event":"error","wall_time":101,"data":{"type":"X"}}\n')
    assert store.snapshot('one', cursor)['reset']


def test_media_paths_deny_traversal_symlinks_and_credentials(tmp_path):
    from drone_agent.dashboard import RunStore
    a = Artifacts(tmp_path/'one', Config())
    a.observe(obs(1))
    store = RunStore(tmp_path)
    assert store.file_path('one', 'frames/frame_000001.png').is_file()
    (a.directory/'frames/escape.png').symlink_to(tmp_path/'secret')
    for name in ('../secret', 'frames/escape.png', 'api/key.json', '.env', 'evaluation/truth.jsonl'):
        with pytest.raises(FileNotFoundError):
            store.file_path('one', name)
    with pytest.raises(FileNotFoundError):
        store.run_path('../one')


def test_photo_provenance_and_reviews_survive_dashboard_projection(tmp_path):
    from drone_agent.dashboard import RunStore
    a = Artifacts(tmp_path/'one', Config(framing_policy='flexible'))
    a.capture(obs(1))
    a.crop_photo({'source_id':'shot_000001','left':0,'top':0,'width':2,'height':3,'degradation_reason':'Thumbnail fixture.'})
    snap = RunStore(tmp_path).snapshot('one', 0)
    photos = snap['state']['photos']
    assert [p['kind'] for p in photos] == ['capture','crop']
    assert photos[1]['source_shot_id'] == 'shot_000001'
    assert photos[1]['source_sha256'] == photos[0]['sha256']


def test_preview_contains_only_public_observation_and_matching_crop(tmp_path):
    from drone_agent.preview import PreviewWriter
    pixels = np.zeros((12,16,3), np.uint8); pixels[:,:,2] = 230
    _, encoded = cv2.imencode('.png', pixels)
    observation = obs(1).model_copy(update={'image_png':encoded.tobytes()})
    writer = PreviewWriter(tmp_path)
    writer.offer(observation, {'version':2,'rectangle':{'left':2,'top':3,'width':4,'height':6}})
    deadline = time.monotonic()+2
    while not (tmp_path/'preview.json').exists() and time.monotonic()<deadline:
        time.sleep(.01)
    writer.close()
    meta = json.loads((tmp_path/'preview.json').read_text())
    assert meta['frame_id'] == 'frame_000001'
    assert meta['photo_frame']['version'] == 2
    assert set(meta['observation']) == {'frame_id','captured_at','image_age_s','battery_pct','connected','airborne','landed'}
    photo = cv2.imread(str(tmp_path/meta['photo_path']))
    assert photo.shape == (6,4,3)
    assert photo[0,0,2] > 200 and photo[0,0,0] < 10
    assert not (tmp_path/'images.json').exists()


def test_provider_credentials_do_not_cross_routes_or_mutate_environment(tmp_path, monkeypatch):
    from drone_agent.dashboard_control import provider_environment, provider_options
    env = tmp_path/'credentials'
    env.write_text('BASE_URL=https://openlux.test/\nAPI_KEY=openlux-secret\nAliCloud_url=https://ali.test/v1\nAliCloud_key=ali-secret\n')
    monkeypatch.setenv('DRONE_PHOTO_VLM_API_KEY','ambient-secret')
    selected = provider_environment('alicloud', env)
    assert selected['DRONE_PHOTO_VLM_API_KEY'] == 'ali-secret'
    assert selected['DRONE_PHOTO_VLM_BASE_URL'] == 'https://ali.test/v1'
    import os
    assert os.environ['DRONE_PHOTO_VLM_API_KEY'] == 'ambient-secret'
    assert 'secret' not in json.dumps(provider_options(env))
    env.write_text('BASE_URL=https://openlux.test/\nAPI_KEY=openlux-secret\n')
    with pytest.raises(ValueError):
        provider_environment('alicloud', env)


def test_local_http_controls_require_origin_and_token(tmp_path):
    from drone_agent.dashboard import make_server
    server = make_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    conn = HTTPConnection('127.0.0.1',server.server_port)
    try:
        conn.request('GET','/api/control')
        response=conn.getresponse(); state=json.loads(response.read())
        assert response.status == 200
        conn.request('POST','/api/control/stop','{}',{'Content-Type':'application/json'})
        response=conn.getresponse(); response.read(); assert response.status == 403
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{server.server_port}',
                 'X-Drone-Control-Token':state['token']}
        conn.request('POST','/api/control/stop','{}',headers)
        response=conn.getresponse(); response.read(); assert response.status == 202
        conn.request('GET','/api/runs',headers={'Host':'evil.test'})
        response=conn.getresponse(); response.read(); assert response.status == 403
    finally:
        conn.close(); server.shutdown(); server.server_close(); thread.join()


def test_control_lifecycle_stop_and_cross_server_exclusion(tmp_path):
    from drone_agent.dashboard_control import ControlConflict, WebotsController
    fake = tmp_path/'webots'
    fake.write_text('''#!/usr/bin/env python3
import json,os,time
from pathlib import Path
p=Path(os.environ['DRONE_AGENT_RUN'])
(p/'trace.jsonl').write_text('')
while not (p/'stop.request').exists():time.sleep(.01)
(p/'summary.json').write_text(json.dumps({'status':'aborted','reason':'operator_stop','shots':[], 'landed':True}))
''')
    fake.chmod(0o700)
    controller = WebotsController(tmp_path/'runs',webots=fake)
    other = WebotsController(tmp_path/'runs',webots=fake)
    request = {'provider':'scripted','model':'scripted','brief':'engineering check','duration_s':30}
    try:
        started = controller.start(request)
        run = tmp_path/'runs'/started['active_run']
        with pytest.raises(ControlConflict):
            controller.start(request)
        with pytest.raises(ControlConflict):
            other.start(request)
        assert controller.stop()['state'] == 'stopping'
        deadline = time.monotonic()+8
        while controller.snapshot()['busy'] and time.monotonic()<deadline:
            time.sleep(.03)
        assert not controller.snapshot()['busy']
        assert (run/'stop.request').exists()
        assert json.loads((run/'summary.json').read_text())['reason'] == 'operator_stop'
        assert 'API_KEY' not in json.dumps(controller.snapshot())
    finally:
        controller.close(); other.close()


def test_live_preview_advances_while_model_request_is_pending(tmp_path):
    from drone_agent.agent import AgentLoop
    from drone_agent.preview import PreviewWriter
    from drone_agent.runtime import Runtime
    from test_loop_runtime import Backend, Policy
    from native_helpers import reply
    config = Config()
    artifacts = Artifacts(tmp_path/'run',config)
    preview = PreviewWriter(artifacts.directory,fps=100)
    backend = Backend()
    samples = []
    def slow_request(messages):
        for _ in range(4):
            time.sleep(.06)
            path = artifacts.directory/'preview.json'
            if path.exists():samples.append(json.loads(path.read_text())['frame_id'])
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply('finish',{'shot_id':None,'abandon':True},frame=current)
    try:
        result=AgentLoop(Runtime(backend,config,artifacts,preview=preview),Policy([slow_request]),artifacts,config).run()
    finally:
        preview.close()
    assert result['reason'] == 'agent_abandoned'
    assert len(set(samples))>=3
    events=[json.loads(line) for line in artifacts.trace.read_text().splitlines()]
    observations=[e for e in events if e['event']=='observation']
    assert len(observations)==2
    started=next(e for e in events if e['event']=='inference_started')
    finished=next(e for e in events if e['event']=='inference_finished')
    end=next(e for e in events if e['event']=='round_end')
    assert observations[0]['monotonic']<started['monotonic']
    assert observations[1]['monotonic']>finished['monotonic']
    assert observations[1]['data']['frame_id']==end['data']['frame_id']


def test_standalone_report_keeps_embedded_photo_evidence(tmp_path):
    import base64
    from drone_agent.dashboard import RunStore
    a = Artifacts(tmp_path/'one',Config())
    photo=a.capture(obs(1))
    (a.directory/'report.html').write_text('<html><img src="shots/shot_000001.png"></html>')
    report=RunStore(tmp_path).report('one')
    assert b'data:image/png;base64,'+base64.b64encode(a.image(photo['id']).read_bytes()) in report


def test_launcher_bounds_stop_even_when_controller_never_initializes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from drone_agent import cli
    elapsed=[0.]
    run=tmp_path/'run'
    def sleep(seconds):
        elapsed[0]+=seconds
        (run/'stop.request').touch()
    class HungWebots:
        pid=1
        returncode=None
        def __init__(self,*args,**kwargs):pass
        def poll(self):return self.returncode
        def terminate(self):self.returncode=-15
        def wait(self,timeout=None):return self.returncode
    monkeypatch.setattr(cli,'time',SimpleNamespace(monotonic=lambda:elapsed[0],sleep=sleep,time=lambda:1000.))
    monkeypatch.setattr(cli.subprocess,'Popen',HungWebots)
    monkeypatch.setattr(cli,'source_manifest',lambda:{})
    cli.launch(Config(duration_s=900.,recovery_s=2.),run)
    summary=json.loads((run/'summary.json').read_text())
    assert elapsed[0]<10
    assert summary['reason']=='operator_stop_no_summary'
