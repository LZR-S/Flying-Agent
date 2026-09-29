"""Post-capture review must precede ordinary task actions, without delaying recovery."""
import json
import time

import httpx
import pytest

from drone_agent.agent import AgentLoop
from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from drone_agent.protocol import Config
from native_helpers import reply, review_arguments
from test_cropping import crop_arguments, labels
from test_loop_runtime import Policy, setup
from test_protocol_context import obs, images


def trace(artifacts):
    return [json.loads(line) for line in artifacts.trace.read_text().splitlines()]


@pytest.mark.parametrize('blocked_tool,arguments',[
    ('act',{'kind':'land'}), ('act',{'kind':'left','value':20}), ('act',{'kind':'hold','value':0}),
    ('capture',{}), ('crop_photo',crop_arguments()),
    ('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':{'left':3,'top':2,'width':6,'height':9}}),
    ('photo_frame',{'mode':'clear'}),
    ('finish',{'shot_id':None,'abandon':True}),
])
def test_new_capture_blocks_normal_actions_until_review(blocked_tool,arguments,tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    policy=Policy([('act',{'kind':'takeoff'}),('capture',{}),(blocked_tool,arguments),
                   ('review_photo',review_arguments()),('act',{'kind':'land'}),
                   ('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    rows=trace(a)
    rejected=next(e['data'] for e in rows if e['event']=='tool_result' and e['data']['round']==3)
    assert rejected['status']=='rejected' and rejected['reason']=='photo_review_pending'
    assert rejected['pending_review_id']=='shot_000001'
    assert result['status']=='completed' and result['pending_review_id'] is None
    assert result['action_requests']==2 and len(a.shots)==1 and not a.crops
    review_index=next(i for i,e in enumerate(rows) if e['event']=='photo_review')
    land_index=next(i for i,e in enumerate(rows) if e['event']=='action_started' and e['data']['action']['kind']=='land')
    assert review_index<land_index
    assert b.sent==['takeoff','land']


def test_review_then_model_adjustment_recapture_and_review_precede_landing(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    first=review_arguments() | {'next_step':'continue','quality_issues':['Reduce excess foreground.'],
                               'rationale':'Adjust the viewpoint, then check the next exposure.'}
    p=Policy([('act',{'kind':'takeoff'}),('capture',{}),('review_photo',first),
              ('act',{'kind':'left','value':20}),('capture',{}),
              ('act',{'kind':'land'}),('review_photo',review_arguments('shot_000002')),
              ('act',{'kind':'land'}),('finish',{'shot_id':'shot_000002'})])
    result=AgentLoop(r,p,a,config).run()
    rows=trace(a)
    actions=[e['data'] for e in rows if e['event']=='action_started']
    assert [e['action_id'] for e in actions]==['native:call_1','native:call_4','native:call_8']
    assert result['status']=='completed' and len(a.reviews)==2
    checkpoints=[e['data'] for e in rows if e['event']=='review_checkpoint']
    assert [(c['status'],c['image_id']) for c in checkpoints]==[
        ('required','shot_000001'),('completed','shot_000001'),
        ('required','shot_000002'),('completed','shot_000002')]
    assert all(c['airborne'] for c in checkpoints)


def test_pending_image_survives_protocol_error_and_rejected_replay(tmp_path):
    config,a,b,r=setup(tmp_path,navigation_history=False)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    seen=[]
    def review(messages):
        state=json.loads(messages[-1]['content'][0]['text'])
        seen.append(state['pending_review_id'])
        assert {'frame_','shot_'}=={label['id'].split('_')[0]+'_' for label in labels(messages)}
        return reply('review_photo',review_arguments(),frame=state['current']['frame_id'],call_id='corrected')
    malformed=review_arguments() | {'checks':[]}
    p=Policy([('capture',{}),('review_photo',malformed),('view_images',{'image_ids':['frame_999999']}),review,
              ('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed' and seen==['shot_000001']
    assert len(a.reviews)==1


def test_new_crop_cannot_clear_checkpoint_by_reviewing_original(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('act',{'kind':'takeoff'}),('capture',{}),('review_photo',review_arguments()),
              ('crop_photo',crop_arguments()),('review_photo',review_arguments()),
              ('act',{'kind':'land'}),('review_photo',review_arguments('crop_000001',status='unknown')),
              ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,p,a,config).run()
    denied=[e['data'] for e in trace(a) if e['event']=='tool_result' and e['data']['status']=='rejected']
    assert [d['round'] for d in denied]==[5,6]
    assert all(d['reason']=='photo_review_pending' for d in denied)
    assert len(a.reviews)==2 and result['status']=='partial'
    assert result['action_requests']==2


def test_framed_capture_requires_framed_candidate_review_not_original(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    box={k:v for k,v in crop_arguments().items() if k in ('left','top','width','height')}
    p=Policy([('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':box}),('capture',{}),
              ('review_photo',review_arguments()),('review_photo',review_arguments('crop_000001')),
              ('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed' and len(a.reviews)==1
    assert a.reviews[0]['image_id']=='crop_000001'
    assert 'photo_review_pending' in a.trace.read_text()


@pytest.mark.parametrize('history',[False,True])
def test_pending_candidate_is_pinned_when_explicit_comparison_fills_slots(tmp_path,history):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    for n in range(1,5):a.capture(obs(n))
    a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':{'left':3,'top':2,'width':6,'height':9}},obs(4))
    c=ContextBuilder(a,'test',navigation_history=history)
    c.request_images(['shot_000001','shot_000002','shot_000003'],'frame_000004')
    messages=c.build(obs(5),{},pending_review_id='shot_000004')
    assert [p['image_id'] for p in labels(messages)]==['frame_000005','shot_000004','shot_000001','shot_000002']
    state=json.loads(messages[-1]['content'][0]['text'])
    assert state['pending_review_id']=='shot_000004'
    assert state['omitted_requested_image_ids']==['shot_000003']
    assert labels(messages)[0]['viewfinder']['source_frame_id']=='frame_000005'
    assert len(images(messages))==4
    followup=c.build(obs(6),{},pending_review_id='shot_000004')
    assert 'shot_000004' in [p['image_id'] for p in labels(followup)]
    assert len(images(followup))<=4


def test_stop_remains_available_during_review_without_clearing_checkpoint(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('act',{'kind':'takeoff'}),('capture',{}),('act',{'kind':'stop'}),
              ('act',{'kind':'land'}),('review_photo',review_arguments()),
              ('act',{'kind':'land'}),('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed'
    assert b.sent==['takeoff','stop','land']
    denied=[e['data'] for e in trace(a) if e['event']=='tool_result' and e['data']['status']=='rejected']
    assert [d['round'] for d in denied]==[4]


@pytest.mark.parametrize('fault,reason',[
    ('battery','low_battery'),('cancel','operator_stop'),('boundary','boundary_violation'),
    ('deadline','mission_deadline'),('api','api_error'),('timeout','api_timeout'),('step_budget','step_budget'),
])
def test_recovery_lands_with_unreviewed_photo_and_preserves_pending_state(tmp_path,fault,reason):
    config,a,b,r=setup(tmp_path,max_steps=2 if fault=='step_budget' else 10,
                       api_timeout_s=.02 if fault=='timeout' else 90.)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    # Inject external faults after a saved photo, during the next inference.
    def fault_policy(messages):
        assert json.loads(messages[-1]['content'][0]['text'])['pending_review_id']=='shot_000001'
        if fault=='api':raise httpx.ConnectError('test API connection failure')
        if fault=='battery':
            base_observe=b.observe
            b.observe=lambda:base_observe().model_copy(update={'battery_pct':10.})
        if fault=='cancel':(a.directory/'stop.request').touch()
        if fault=='boundary':
            (a.directory/'evaluation').mkdir();(a.directory/'evaluation/abort.signal').touch()
        if fault=='deadline':r.deadline=0
        time.sleep(.08 if fault=='timeout' else .01)
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply('act',{'kind':'land'},frame=current,call_id='late')
    p=Policy([('act',{'kind':'takeoff'}),('capture',{}),fault_policy])
    result=AgentLoop(r,p,a,config).run()
    assert result['reason']==reason and result['pending_review_id']=='shot_000001'
    assert result['landed'] and result['landing']['source']=='recovery'
    assert len(a.shots)==1 and not a.reviews and result['selected_id'] is None
    assert b.sent==['takeoff','land']


def test_reviewed_frame_does_not_allow_delivering_unreviewed_original(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    box={k:v for k,v in crop_arguments().items() if k in ('left','top','width','height')}
    p=Policy([('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':box}),('act',{'kind':'takeoff'}),('capture',{}),
              ('review_photo',review_arguments('crop_000001')),('act',{'kind':'land'}),
              ('finish',{'shot_id':'shot_000001'}),('review_photo',review_arguments()),
              ('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed' and result['selected_id']=='shot_000001'
    assert len(a.reviews)==2 and result['selected_review']['image_id']=='shot_000001'
    denied=[e['data'] for e in trace(a) if e['event']=='tool_result' and e['data']['status']=='rejected']
    assert len(denied)==1 and denied[0]['round']==6 and denied[0]['reason']=='review_required'
