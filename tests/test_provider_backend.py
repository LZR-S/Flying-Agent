import json
import httpx
import pytest
from drone_agent.provider import CloudPolicy
from drone_agent.webots_backend import CommandState
from drone_agent.protocol import Action, Config
from drone_agent.artifacts import Artifacts
from native_helpers import reply
from backends import FakeFlight


@pytest.mark.parametrize('model',['gemini-3.6-flash','qwen3.8-flash','gpt-6-astra'])
@pytest.mark.parametrize('framing_policy',['max_native','flexible'])
def test_eight_tool_protocol_round_trip_and_prompts_are_consistent(tmp_path,model,framing_policy):
    from drone_agent.agent import AgentLoop
    from test_loop_runtime import setup
    config,a,b,r=setup(tmp_path,model=model,framing_policy=framing_policy)
    requests=[]
    choices=[('photo_frame',{'mode':'set','aspect_ratio':'2:3'}),
             ('photo_frame',{'mode':'guides','guides':'golden'}),
             ('photo_frame',{'mode':'clear'}),('finish',{'shot_id':None,'abandon':True})]
    def handler(request):
        payload=json.loads(request.content)
        requests.append(payload)
        tools={t.get('function',t)['name']:t.get('function',t) for t in payload['tools']}
        assert set(tools)=={'act','capture','crop_photo','photo_frame','generate_reference','review_photo','view_images','finish'}
        schema=tools['photo_frame']['parameters']
        assert schema['properties']['rectangle']['type']=='object'
        assert 'anyOf' not in json.dumps(schema) and 'oneOf' not in schema
        assert 'mode' in schema['required'] and 'rectangle' not in schema['required']
        messages=payload['input'] if model=='gpt-6-astra' else payload['messages']
        system=messages[0]['content']
        assert 'automatically' in system and 'hold' in system
        assert not any(name in system for name in ('set_photo_frame','clear_photo_frame'))
        state=json.loads(messages[-1]['content'][0]['text'])
        assert state['round']==len(requests)
        if len(requests)==2:
            assert state['photo_frame']['rectangle']=={'left':4,'top':0,'width':8,'height':12}
            assert state['photo_frame']['resolution']['retained_max_frame_fraction']==1
        if len(requests)==3:
            assert state['photo_frame']['guides']=='golden'
            assert state['photo_frame']['rectangle']=={'left':4,'top':0,'width':8,'height':12}
            label=json.loads(messages[-1]['content'][1]['text'])
            assert label['viewfinder']['guides']=='golden'
        name,arguments=choices[len(requests)-1]
        message=reply(name,arguments,frame=state['current']['frame_id'],call_id=f'call_{len(requests)}')
        if model=='gpt-6-astra':
            call=message['tool_calls'][0]
            return httpx.Response(200,json={'output':[{'type':'function_call','id':f'fc_{len(requests)}',
                'call_id':call['id'],**call['function']}]})
        return httpx.Response(200,json={'choices':[{'message':message}]})
    policy=CloudPolicy(config,a,base_url='https://test.invalid/v1',api_key='test',
                       transport=httpx.MockTransport(handler))
    result=AgentLoop(r,policy,a,config).run()
    assert result['reason']=='agent_abandoned' and len(requests)==4
    if framing_policy=='flexible':
        assert a.photo_frame=={'version':3,'rectangle':None}
    else:
        assert a.photo_frame['version']==2 and a.photo_frame['rectangle']['height']==12
        assert 'frame_contract_locked' in a.trace.read_text()
    assert b.sent==[]


def test_provider_retries_only_http_request_and_records_usage_without_key(tmp_path):
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls)==1:return httpx.Response(503)
        return httpx.Response(200,json={'choices':[{'message':reply('photo_frame',{'mode':'clear'})}],
          'usage':{'prompt_tokens':21,'completion_tokens':3,'total_tokens':24}})
    a=Artifacts(tmp_path/'run',Config())
    p=CloudPolicy(Config(),a,base_url='https://test.invalid/v1',api_key='SECRET_TEST_KEY',transport=httpx.MockTransport(handler))
    assert p.complete([{'role':'user','content':'hello'}])==reply('photo_frame',{'mode':'clear'})
    assert p.attempts==2
    assert calls[0]==calls[1]
    assert calls[0]['temperature']==0
    assert 'reasoning_effort' not in calls[0]
    assert 'enable_thinking' not in calls[0]
    for path in a.directory.rglob('*.json*'):assert 'SECRET_TEST_KEY' not in path.read_text()
    assert '24' in (a.directory/'api-metrics.jsonl').read_text()


def test_provider_attempt_budget_survives_retries(tmp_path):
    a=Artifacts(tmp_path/'run',Config(max_api_attempts=1))
    p=CloudPolicy(Config(max_api_attempts=1),a,base_url='https://test.invalid',api_key='x',
                  transport=httpx.MockTransport(lambda _:httpx.Response(503)))
    with pytest.raises(Exception):p.complete([])
    assert p.attempts==1
    with pytest.raises(Exception):p.complete([])
    assert p.attempts==1


def test_jpeg_request_record_matches_transmitted_images_on_retry(tmp_path):
    import base64
    import hashlib
    from drone_agent.audit import audit_requests
    from drone_agent.context import ContextBuilder
    from test_protocol_context import obs, images

    a=Artifacts(tmp_path/'run',Config())
    a.configure_photo_frame({'mode':'clear'},obs())
    photo=a.capture(obs())
    context=ContextBuilder(a,'test')
    context.request_images([photo['id']],'frame_000001')
    messages=context.build(obs(),{})
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(503) if len(calls)==1 else httpx.Response(
            200,json={'choices':[{'message':reply('photo_frame',{'mode':'clear'})}]})
    p=CloudPolicy(Config(),a,base_url='https://test.invalid/v1',api_key='test',
                  transport=httpx.MockTransport(handler))
    assert p.complete(messages)==reply('photo_frame',{'mode':'clear'})
    saved=json.loads((a.directory/'api/call_000001.request.json').read_text())
    assert saved==calls[0]==calls[1]
    url=images(saved['messages'])[0]['image_url']['url']
    assert url.startswith('data:image/jpeg;base64,')
    data=base64.b64decode(url.split(',',1)[1],validate=True)
    audit=audit_requests(a.directory)
    assert audit['status']=='passed'
    assert audit['requests'][0]['images']==[{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}]
    assert [label['image_id'] for label in audit['requests'][0]['image_labels']]==['frame_000001','shot_000001']
    metrics=[json.loads(line) for line in (a.directory/'api-metrics.jsonl').read_text().splitlines()]
    assert metrics[0]['context']==metrics[1]['context']
    assert metrics[0]['context']['image_count']==1
    assert metrics[0]['context']['deduplicated_image_count']==1
    assert metrics[0]['context']['image_bytes']==len(data)
    assert metrics[0]['context']['round']==1
    assert a.image('frame_000001').read_bytes()==obs().image_png

def test_input_audit_checks_navigation_aliases_under_ablation(tmp_path):
    from drone_agent.artifacts import write_json
    from drone_agent.audit import audit_requests
    from drone_agent.context import ContextBuilder
    from test_protocol_context import obs
    a=Artifacts(tmp_path/'run',Config(navigation_history=False))
    messages=ContextBuilder(a,'test',navigation_history=False).build(obs(2),{})
    label=json.loads(messages[-1]['content'][1]['text'])
    label['aliases']=[{'image_id':'frame_000001','kind':'navigation','current':False,'captured_at':1.}]
    messages[-1]['content'][1]['text']=json.dumps(label)
    write_json(a.directory/'api/call_000001.request.json',{'messages':messages})
    write_json(a.directory/'launch.json',{'navigation_history':False})
    audit=audit_requests(a.directory)
    assert audit['status']=='failed'
    assert audit['violations'][0]['kind']=='old_navigation_image'


def test_qwen_flash_uses_non_thinking_native_tools(tmp_path):
    config=Config(model='qwen3.8-flash')
    artifacts=Artifacts(tmp_path/'run',config)
    calls=[]
    def handler(request):
        payload=json.loads(request.content)
        calls.append(payload)
        if payload.get('enable_thinking') is not False:
            return httpx.Response(400,json={'error':'non_thinking_mode_required'})
        return httpx.Response(200,json={'choices':[{'message':reply('photo_frame',{'mode':'clear'})}]})
    policy=CloudPolicy(config,artifacts,base_url='https://test.invalid/v1',api_key='test',
                       transport=httpx.MockTransport(handler))
    assert policy.complete([{'role':'user','content':'Disable photo framing.'}])==reply('photo_frame',{'mode':'clear'})
    assert calls[0]['temperature']==0
    assert calls[0]['tools'] and calls[0]['parallel_tool_calls'] is False
    assert calls[0]['tool_choice']=='required'
    assert 'reasoning_effort' not in calls[0]
    saved=json.loads((artifacts.directory/'api/call_000001.request.json').read_text())
    assert saved==calls[0]


def test_astra_uses_medium_reasoning_without_sampling_parameters(tmp_path):
    config=Config(model='gpt-6-astra')
    artifacts=Artifacts(tmp_path/'run',config)
    calls=[]
    def handler(request):
        payload=json.loads(request.content)
        calls.append(payload)
        for tool in payload['tools']:
            schema=tool.get('parameters',tool.get('function',{}).get('parameters',{}))
            if schema.get('type')!='object' or set(schema)&{'oneOf','anyOf','allOf','enum','const','not'}:
                return httpx.Response(400,json={'error':{'code':'invalid_function_parameters'}})
        assert request.url.path=='/v1/responses'
        return httpx.Response(200,json={'output':[{'type':'function_call','id':'fc_test','call_id':'call_test',
            'name':'photo_frame','arguments':reply('photo_frame',{'mode':'clear'})['tool_calls'][0]['function']['arguments']}]})
    policy=CloudPolicy(config,artifacts,base_url='https://test.invalid/v1',api_key='test',
                       transport=httpx.MockTransport(handler))
    assert policy.complete([{'role':'user','content':'Disable photo framing.'}])==reply('photo_frame',{'mode':'clear'})
    assert calls[0]['reasoning']=={'effort':'medium'}
    assert calls[0]['store'] is False and 'previous_response_id' not in calls[0]
    assert calls[0]['include']==['reasoning.encrypted_content']
    assert 'temperature' not in calls[0] and 'enable_thinking' not in calls[0]
    assert calls[0]['tools'] and calls[0]['parallel_tool_calls'] is False
    assert calls[0]['tool_choice']=='auto'
    assert json.loads((artifacts.directory/'api/call_000001.request.json').read_text())==calls[0]
    from drone_agent.protocol import native_tool_definitions, parse_tool_decision
    act=next(t['function']['parameters'] for t in native_tool_definitions() if t['function']['name']=='act')
    assert len(act['oneOf'])==13
    with pytest.raises(ValueError):
        parse_tool_decision(reply('act',{'kind':'forward','value':1}))


class Flight(FakeFlight):
    """The shared fake, fixed at the starting pose these tests assume."""

    def __init__(self):
        super().__init__(position=(10.,20.,1.6),yaw=0.)


def test_body_direction_is_relative_and_timeout_cannot_report_completed():
    f=Flight(); c=CommandState(f,Action(kind='left',value=200),'a')
    assert c.destination==[8.,20.,1.6]
    assert c.poll() is None
    f.elapsed_s=100
    assert c.poll().status=='unknown'


def test_land_timeout_does_not_claim_touchdown_or_cut_motors():
    f=Flight();c=CommandState(f,Action(kind='land',value=0),'a')
    f.elapsed_s=100
    assert c.poll().status=='unknown'
    assert f.flying


def test_land_completes_only_after_low_and_stable():
    f=Flight();c=CommandState(f,Action(kind='land',value=0),'a')
    f.reached=True
    assert c.poll() is None
    f.altitude_m=.1; f.position=(10.,20.,.1)
    f.elapsed_s=3.5
    assert c.poll() is None
    f.elapsed_s=4.1
    assert c.poll().status=='completed'
    assert not f.flying


def test_text_json_is_not_silently_used_as_a_native_tool_call(tmp_path):
    from drone_agent.protocol import parse_tool_decision
    p=CloudPolicy(Config(),Artifacts(tmp_path/'run',Config()),base_url='https://test.invalid',api_key='x',
        transport=httpx.MockTransport(lambda _:httpx.Response(200,json={
            'choices':[{'message':{'role':'assistant','content':'{"tool":"observe"}'}}]})))
    with pytest.raises(ValueError,match='native_tool_call_required'):
        parse_tool_decision(p.complete([]))


def test_full_rotation_tracks_directed_turn_instead_of_wrapping_to_zero():
    import math
    f=Flight();f.reached=True;f.yaw=0.
    c=CommandState(f,Action(kind='cw',value=360),'a')
    assert c.poll() is None
    assert 0 < f.target_yaw <= math.pi/2
    for step in range(1,5):
        f.yaw=math.atan2(math.sin(step*math.pi/2),math.cos(step*math.pi/2))
        f.elapsed_s=step
        result=c.poll()
        if step<4:assert result is None
    assert result.status=='completed'


def test_capture_forces_new_camera_exposure_without_channel_swap():
    from collections import deque
    from types import SimpleNamespace
    import cv2
    import numpy as np
    from drone_agent.webots_backend import WebotsBackend
    backend=WebotsBackend.__new__(WebotsBackend)
    backend.config=Config();backend.seq=0;backend.images=deque(maxlen=100)
    backend.flight=Flight();backend.battery=100.;backend.connected=True;backend.last_image_sim=-1
    pixels=np.array([[[10,20,240,255]]],dtype=np.uint8)
    backend.camera=SimpleNamespace(getImage=lambda:pixels.tobytes(),getWidth=lambda:1,getHeight=lambda:1)
    backend.tick=lambda:None
    first=backend.capture();pixels[0,0]=[30,40,50,255]
    second=backend.capture()
    assert first.frame_id!=second.frame_id
    decoded=cv2.imdecode(np.frombuffer(second.image_png,np.uint8),cv2.IMREAD_COLOR)
    assert decoded[0,0].tolist()==[30,40,50]
