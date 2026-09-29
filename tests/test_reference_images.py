import base64
import json
import time

import cv2
import httpx
import numpy as np
import pytest

from drone_agent.agent import AgentLoop
from drone_agent.context import ContextBuilder
from drone_agent.protocol import Config, parse_tool_decision
from drone_agent.reference import ReferenceGenerator
from native_helpers import reply, review_arguments
from test_loop_runtime import Policy, setup
from test_protocol_context import obs


def generated():
    pixels=np.full((384,256,3),(30,80,190),np.uint8)
    ok,png=cv2.imencode('.png',pixels);assert ok
    return {'image':png.tobytes(),'model':'gpt-image-2','usage':{'total_tokens':50},
            'parameters':{'model':'gpt-image-2','quality':'medium','size':'1024x1536','output_format':'png','n':1}}


class Generator:
    def __init__(self,delay=0,error=None):self.calls=[];self.delay=delay;self.error=error
    def generate(self,**kwargs):
        self.calls.append(kwargs);time.sleep(self.delay)
        if self.error:raise self.error
        return generated()


def generate_call(messages):
    state=json.loads(messages[-1]['content'][0]['text'])
    return reply('generate_reference',{'source_id':state['current']['frame_id'],
                 'guidance':'Preserve the scene and show head to thighs.','aspect_ratio':'2:3'},
                 frame=state['current']['frame_id'],call_id=f"reference_{state['round']}")


def comparison(use=True):
    return {'reference_id':'ref_000001','use_reference':use,
            'reason':'Compare the intended framing against the real scene; reject fabricated details.',
            'differences':['The real photograph contains more foreground than the synthetic reference.']}


def test_generator_sends_grounded_edit_and_keeps_credentials_out_of_evidence(tmp_path):
    config,a,_,_=setup(tmp_path)
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.path=='/v1/images/edits'
        assert request.headers['Authorization']=='Bearer private-reference-key'
        assert obs().image_png in request.content
        assert config.brief.encode() in request.content
        assert b'fixed camera' in request.content and b'gpt-image-2' in request.content
        return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(generated()['image']).decode()}],
                                       'usage':{'total_tokens':50}})
    service=ReferenceGenerator(config,a,base_url='https://example.invalid',api_key='private-reference-key',
                               transport=httpx.MockTransport(handler))
    result=service.generate(source_id='frame_000001',source=obs().image_png,guidance='Head to thighs.',
                            aspect_ratio='2:3',call_id='ref_request_000001')
    assert result['image']==generated()['image'] and len(calls)==1
    for path in (a.directory/'reference-api').glob('*.json'):
        assert 'private-reference-key' not in path.read_text()
    request=json.loads((a.directory/'reference-api/ref_request_000001.request.json').read_text())
    assert 'height_m' not in json.dumps(request)


@pytest.mark.parametrize('status,payload',[
    (503,{}),(200,{'data':[{'url':'https://untrusted.invalid/image.png'}]}),
    (200,{'data':[{'b64_json':base64.b64encode(b'not a PNG').decode()}]}),
])
def test_generation_failure_does_not_retry_or_download_external_urls(tmp_path,status,payload):
    config,a,_,_=setup(tmp_path);calls=[]
    def handler(request):calls.append(request);return httpx.Response(status,json=payload)
    service=ReferenceGenerator(config,a,base_url='https://example.invalid',api_key='test',
                               transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        service.generate(source_id='frame_000001',source=obs().image_png,guidance='Natural framing.',
                         aspect_ratio='2:3',call_id='ref_request_000001')
    assert len(calls)==1 and not a.references


def test_reference_flows_into_framing_and_requires_real_photo_comparison(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible');service=Generator();seen=[]
    def frame(messages):
        state=json.loads(messages[-1]['content'][0]['text']);seen.append(state)
        assert state['composition_reference']['id']=='ref_000001'
        assert state['composition_reference']['synthetic'] is True
        return reply('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':{'left':3,'top':2,'width':6,'height':9}},
                     frame=state['current']['frame_id'],call_id='frame')
    policy=Policy([('act',{'kind':'takeoff'}),generate_call,frame,('capture',{}),
                   ('review_photo',review_arguments('crop_000001')),
                   ('review_photo',review_arguments('crop_000001')|{'reference_comparison':comparison()}),
                   ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config,reference_generator=service).run()
    assert result['status']=='completed' and len(service.calls)==1
    assert b.sent==['takeoff','land'] and len(a.references)==1
    assert len(a.shots)==len(a.crops)==len(a.reviews)==1
    assert 'reference_comparison_required' in a.trace.read_text()
    assert result['selected_review']['reference_comparison']['reference_id']=='ref_000001'
    assert result['reference_attempts']==1 and result['action_requests']==2


@pytest.mark.parametrize('failure',['error','timeout','cancel'])
def test_generation_wait_services_runtime_and_cannot_activate_late_reference(tmp_path,failure):
    config,a,b,r=setup(tmp_path,reference_timeout_s=.02)
    b.airborne=True
    service=Generator(delay=.08 if failure!='error' else 0,error=ValueError('reference_http_error') if failure=='error' else None)
    if failure=='cancel':
        original=b.tick
        def tick():
            original()
            if service.calls:(a.directory/'stop.request').touch()
        b.tick=tick
    policy=Policy([generate_call,('act',{'kind':'land'}),('finish',{'shot_id':None,'abandon':True})])
    result=AgentLoop(r,policy,a,config,reference_generator=service).run()
    time.sleep(.1)
    assert not a.references and len(service.calls)==1 and b.seq>2
    assert result['reason']==('operator_stop' if failure=='cancel' else 'agent_abandoned')
    assert b.sent==['land']
    assert result['landing']['source']==('recovery' if failure=='cancel' else 'model')


def test_synthetic_reference_cannot_be_delivered_cropped_or_used_as_navigation(tmp_path):
    for tool,args in [('finish',{'shot_id':'ref_000001'}),
                      ('crop_photo',{'source_id':'ref_000001','left':0,'top':0,'width':4,'height':6}),
                      ('generate_reference',{'source_id':'ref_000001','guidance':'x','aspect_ratio':'2:3'}),
                      ('review_photo',review_arguments('ref_000001'))]:
        with pytest.raises(ValueError):parse_tool_decision(reply(tool,args))
    with pytest.raises(ValueError):parse_tool_decision(reply('capture',frame='ref_000001'))


def test_reference_ignoring_does_not_relax_user_requirements(tmp_path):
    config,a,b,r=setup(tmp_path);service=Generator()
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    policy=Policy([generate_call,('capture',{}),
                   ('review_photo',review_arguments(status='unsatisfied')|{'reference_comparison':comparison(False)}),
                   ('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,policy,a,config,reference_generator=service).run()
    assert result['status']=='partial' and a.composition_reference is None
    assert len(a.references)==1 and not b.sent


def test_generator_requires_visible_real_source_and_budget(tmp_path):
    config,a,b,r=setup(tmp_path);service=Generator()
    unseen=('generate_reference',{'source_id':'frame_999999','guidance':'x','aspect_ratio':'2:3'})
    p=Policy([unseen,generate_call,generate_call,('finish',{'shot_id':None,'abandon':True})])
    result=AgentLoop(r,p,a,config,reference_generator=service).run()
    assert result['reason']=='agent_abandoned' and len(service.calls)==1
    assert 'reference_source_not_visible' in a.trace.read_text()
    assert 'reference_budget' in a.trace.read_text()


def reference_fixture(a):
    source=a.observe(obs())
    return a.add_reference(generated(),source,request_id='ref_request_000001',tool_call_id='reference')


@pytest.mark.parametrize('navigation_history',[True,False])
def test_reference_context_reserves_real_current_and_pending_photo_without_reviving_navigation(tmp_path,navigation_history):
    config,a,_,_=setup(tmp_path,framing_policy='flexible',navigation_history=navigation_history)
    reference=reference_fixture(a)
    photo=a.capture(obs(2))
    crop=a.crop_photo({'source_id':photo['id'],'left':2,'top':2,'width':6,'height':9,
                       'degradation_reason':'Compare a tighter composition with less detail.'})
    context=ContextBuilder(a,config.brief,navigation_history)
    context.request_photo_comparison(crop,'frame_000003')
    messages=context.build(obs(3),{},pending_review_id=crop['id'])
    assert {reference['id'],crop['id'],'frame_000003',photo['id']}<=context.visible_images.keys()
    assert len([p for p in messages[-1]['content'] if p['type']=='image_url'])==4
    assert context.visible_frames=={'frame_000003'}
    assert 'captured_at' not in reference and reference['source_image_id']=='frame_000001'
    context.request_images([reference['id']],'frame_000004')
    recalled=context.build(obs(4),{})
    assert reference['id'] in context.visible_images and 'frame_000001' not in context.visible_images
    state=json.loads(recalled[-1]['content'][0]['text'])
    assert state['composition_reference']['synthetic'] and reference['id'] in [i['id'] for i in state['image_catalog']]
    if not navigation_history:
        with pytest.raises(ValueError,match='navigation_history_disabled'):
            context.request_images(['frame_000001'],'frame_000004')


@pytest.mark.parametrize('changed',['reference','source'])
def test_reference_comparison_checks_visibility_and_immutable_evidence(tmp_path,changed):
    _,a,_,_=setup(tmp_path)
    ref=reference_fixture(a);photo=a.capture(obs(2))
    arguments=review_arguments()|{'reference_comparison':comparison()}
    visible={photo['id']:photo['sha256']}
    with pytest.raises(ValueError,match='reference_not_visible'):
        a.review_photo(arguments,visible,tool_call_id='review',based_on_frame_id='frame_000002')
    visible[ref['id']]=ref['sha256']
    a.review_photo(arguments,visible,tool_call_id='review',based_on_frame_id='frame_000002')
    assert a.valid_review(photo['id'])
    a.image(ref['id'] if changed=='reference' else ref['source_image_id']).write_bytes(b'changed')
    assert a.valid_review(photo['id']) is None
    with pytest.raises(ValueError,match='image_evidence_changed'):
        a.review_photo(arguments,visible,tool_call_id='review_2',based_on_frame_id='frame_000002')


def test_pending_photo_review_blocks_generation_without_spending_attempt(tmp_path):
    config,a,b,r=setup(tmp_path);service=Generator()
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('capture',{}),generate_call,('review_photo',review_arguments()),('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config,reference_generator=service).run()
    assert result['status']=='completed' and not service.calls and result['reference_attempts']==0
    assert 'photo_review_pending' in a.trace.read_text()


def test_generating_after_a_review_requires_new_comparison_before_delivery(tmp_path):
    config,a,b,r=setup(tmp_path);service=Generator()
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('capture',{}),('review_photo',review_arguments()),generate_call,
              ('finish',{'shot_id':'shot_000001'}),
              ('review_photo',review_arguments()|{'reference_comparison':comparison()}),
              ('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config,reference_generator=service).run()
    assert result['status']=='completed' and len(a.reviews)==2
    assert 'review_required' in a.trace.read_text()


@pytest.mark.parametrize('fault,reason',[('epoch','reference_invalidated'),('battery','low_battery'),
                                        ('deadline','mission_deadline'),('stale','stale_image')])
def test_reference_wait_honors_runtime_authority_and_health(tmp_path,fault,reason):
    config,a,b,r=setup(tmp_path);service=Generator(delay=.02);b.airborne=True
    original=b.tick;observe=b.observe;changed=False
    def tick():
        nonlocal changed
        original()
        if service.calls and not changed:
            changed=True
            if fault=='epoch':r.epoch+=1
            if fault=='deadline':r.deadline=0
            if fault=='battery':b.observe=lambda:observe().model_copy(update={'battery_pct':10.})
            if fault=='stale':b.observe=lambda:observe().model_copy(update={'received_at':0.})
    b.tick=tick
    result=AgentLoop(r,Policy([generate_call]),a,config,reference_generator=service).run()
    time.sleep(.04)
    assert result['reason']==reason and not a.references and b.sent==['land']
    metric=json.loads(next((a.directory/'reference-metrics').glob('*.json')).read_text())
    assert metric['status']=='interrupted' and metric['reason']==reason


def test_reference_errors_never_echo_provider_details_into_policy(tmp_path):
    config,a,b,r=setup(tmp_path);service=Generator(error=RuntimeError('Bearer secret; x_m=123'))
    result=AgentLoop(r,Policy([generate_call,('finish',{'shot_id':None,'abandon':True})]),
                     a,config,reference_generator=service).run()
    assert result['reason']=='agent_abandoned'
    assert 'secret' not in a.trace.read_text() and 'x_m' not in a.trace.read_text()
    assert 'reference_failed' in a.trace.read_text()


def test_image_credentials_are_independent_of_alicloud_decision_provider(tmp_path,monkeypatch):
    import os
    from drone_agent.dashboard_control import _credentials,provider_environment
    from drone_agent.provider import load_credentials
    from drone_agent.reference import reference_environment
    for key in ('BASE_URL','API_KEY','DRONE_PHOTO_IMAGE_BASE_URL','DRONE_PHOTO_IMAGE_API_KEY',
                'DRONE_PHOTO_VLM_BASE_URL','DRONE_PHOTO_VLM_API_KEY'):
        monkeypatch.delenv(key,raising=False)
    path=tmp_path/'credentials'
    path.write_text('BASE_URL=https://openlux.invalid/\nAPI_KEY=image-key\n'
                    'AliCloud_url=https://ali.invalid/v1\nAliCloud_key=decision-key\n')
    decision=provider_environment('alicloud',path)
    image=reference_environment(_credentials(path)|decision)
    assert image=={'DRONE_PHOTO_IMAGE_BASE_URL':'https://openlux.invalid/','DRONE_PHOTO_IMAGE_API_KEY':'image-key'}
    assert decision['DRONE_PHOTO_VLM_API_KEY']=='decision-key'
    assert reference_environment(decision)=={}
    explicit={'DRONE_PHOTO_IMAGE_BASE_URL':'https://image.invalid/v1','DRONE_PHOTO_IMAGE_API_KEY':'separate'}
    assert reference_environment(_credentials(path)|explicit)==explicit
    assert reference_environment(_credentials(path)|{'DRONE_PHOTO_IMAGE_API_KEY':'partial'})=={}
    load_credentials(path)
    assert {k:os.environ[k] for k in image}==image
    for k in image:monkeypatch.delenv(k)
    monkeypatch.setenv('DRONE_PHOTO_VLM_BASE_URL',decision['DRONE_PHOTO_VLM_BASE_URL'])
    monkeypatch.setenv('DRONE_PHOTO_VLM_API_KEY',decision['DRONE_PHOTO_VLM_API_KEY'])
    load_credentials()
    assert not any(os.getenv(k) for k in image)


def test_report_and_dashboard_keep_references_out_of_photo_candidates(tmp_path):
    from drone_agent.dashboard import RunStore
    from drone_agent.evaluation import evaluate_run
    config,a,b,r=setup(tmp_path)
    p=Policy([generate_call,('finish',{'shot_id':None,'abandon':True})])
    AgentLoop(r,p,a,config,reference_generator=Generator()).run()
    evaluation=evaluate_run(a.directory)
    assert evaluation['reference_generation']['generated']==1
    assert evaluation['counts']['photos']==evaluation['counts']['crops']==evaluation['counts']['api_attempts']==0
    assert evaluation['reference_generation']['attempts']==1 and evaluation['selected'] is None
    store=RunStore(tmp_path);snapshot=store.snapshot('run',0)
    assert snapshot['state']['photos']==[] and len(snapshot['state']['references'])==1
    assert snapshot['state']['pending_reference'] is None
    assert store.file_path('run','references/ref_000001.png').is_file()
    with pytest.raises(FileNotFoundError):store.file_path('run','reference-api/ref_request_000001.source.png')
    assert b'Synthetic composition references' in store.report('run')


def test_reference_request_audit_covers_sent_source_bytes(tmp_path):
    from drone_agent.audit import audit_requests
    config,a,_,_=setup(tmp_path)
    client=ReferenceGenerator(config,a,base_url='https://example.invalid/v1',api_key='secret',
        transport=httpx.MockTransport(lambda _:httpx.Response(200,json={
            'data':[{'b64_json':base64.b64encode(generated()['image']).decode()}]})))
    client.generate(source_id='frame_000001',source=obs().image_png,guidance='Natural framing',
                    aspect_ratio='2:3',call_id='ref_request_000001')
    audit=audit_requests(a.directory)
    assert audit['status']=='passed' and len(audit['reference_requests'])==1
    (a.directory/'reference-api/ref_request_000001.source.png').write_bytes(b'changed')
    assert audit_requests(a.directory)['status']=='failed'


def test_ignored_reference_can_be_recalled_and_readopted_with_visible_evidence(tmp_path):
    _,a,_,_=setup(tmp_path)
    ref=reference_fixture(a);photo=a.capture(obs(2))
    visible={ref['id']:ref['sha256'],photo['id']:photo['sha256']}
    a.review_photo(review_arguments()|{'reference_comparison':comparison(False)},visible,
                   tool_call_id='ignore',based_on_frame_id='frame_000002')
    assert a.composition_reference is None and a.valid_review(photo['id'])
    context=ContextBuilder(a,'test')
    context.build(obs(3),{})
    assert ref['id'] not in context.visible_images
    context.request_images([ref['id'],photo['id']],'frame_000004')
    context.build(obs(4),{})
    a.review_photo(review_arguments()|{'reference_comparison':comparison(True)},context.visible_images,
                   tool_call_id='readopt',based_on_frame_id='frame_000004')
    assert a.composition_reference==ref and a.valid_review(photo['id'])['tool_call_id']=='readopt'


def test_reference_schema_is_nonnullable_and_generation_can_be_disabled(tmp_path):
    from drone_agent.protocol import native_tool_definitions
    schemas={t['function']['name']:t['function']['parameters'] for t in native_tool_definitions()}
    comparison_schema=schemas['review_photo']['properties']['reference_comparison']
    assert comparison_schema['type']=='object' and 'anyOf' not in comparison_schema
    assert 'reference_comparison' not in schemas['review_photo']['required']
    assert set(schemas['generate_reference']['required'])=={'source_id','guidance','aspect_ratio','based_on_frame_id','note'}
    config,a,b,r=setup(tmp_path,max_references=0);service=Generator()
    result=AgentLoop(r,Policy([generate_call,('finish',{'shot_id':None,'abandon':True})]),
                     a,config,reference_generator=service).run()
    assert result['reference_attempts']==0 and not service.calls
    assert 'reference_budget' in a.trace.read_text()
