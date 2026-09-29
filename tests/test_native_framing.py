import json

import cv2
import numpy as np
import pytest

from drone_agent.agent import AgentLoop
from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from drone_agent.protocol import Config, parse_tool_decision
from native_helpers import reply, review_arguments
from test_cropping import labels
from test_loop_runtime import Policy, setup
from test_protocol_context import images, obs
from test_reference_images import reference_fixture


@pytest.mark.parametrize('ratio,rectangle', [
    ('2:3', {'left':240,'top':0,'width':480,'height':720}),
    ('4:3', {'left':0,'top':0,'width':960,'height':720}),
    ('1:1', {'left':120,'top':0,'width':720,'height':720}),
    ('16:9', {'left':0,'top':90,'width':960,'height':540}),
    ('4:6', {'left':240,'top':0,'width':480,'height':720}),
])
def test_ratio_selects_maximum_native_frame_and_preserves_exact_exposure(tmp_path, ratio, rectangle):
    pixels=np.arange(720*960*3,dtype=np.uint32).reshape(720,960,3).astype(np.uint8)
    ok,png=cv2.imencode('.png',pixels);assert ok
    exposure=obs().model_copy(update={'image_png':png.tobytes()})
    a=Artifacts(tmp_path/'run',Config())
    setting=a.configure_photo_frame({'mode':'set','aspect_ratio':ratio},exposure)
    assert setting['rectangle']==rectangle
    preview=a.frame_preview(exposure)
    shot=a.capture(exposure)
    crop=a.images[shot['framed_photo_id']]
    x,y,w,h=(rectangle[k] for k in ('left','top','width','height'))
    for item in (preview,crop):
        np.testing.assert_array_equal(cv2.imread(str(a.image(item['id']))),pixels[y:y+h,x:x+w])
        assert item['resolution']==setting['resolution']
        assert item['resolution']['pixel_count']==w*h
        assert item['resolution']['retained_source_fraction']==w*h/(960*720)
        assert item['resolution']['retained_max_frame_fraction']==1
        assert item['resolution']['degraded'] is False
    assert a.image(shot['id']).read_bytes()==png.tobytes()
    assert crop['aspect_ratio']==setting['aspect_ratio']


def test_smaller_frame_requires_explicit_downgrade_without_mutating_state(tmp_path):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    initial=a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3'},obs())
    arguments={'mode':'set','aspect_ratio':'2:3',
               'rectangle':{'left':3,'top':2,'width':6,'height':9}}
    with pytest.raises(ValueError,match='resolution_downgrade_requires_reason'):
        a.configure_photo_frame(arguments,obs())
    assert a.photo_frame==initial
    reason='Remaining flight budget prevents a closer viewpoint; accept reduced detail.'
    frame=a.configure_photo_frame(arguments | {'degradation_reason':reason},obs())
    assert frame['resolution']['maximum_width_px']==8
    assert frame['resolution']['maximum_height_px']==12
    assert frame['resolution']['maximum_pixel_count']==96
    assert frame['resolution']['retained_max_frame_fraction']==54/96
    assert frame['resolution']['degraded'] is True
    assert frame['resolution']['degradation_reason']==reason
    shot=a.capture(obs())
    crop=a.images[shot['framed_photo_id']]
    c=ContextBuilder(a,'2:3 portrait')
    c.record(reply('photo_frame',arguments | {'degradation_reason':reason}),
             {'status':'completed','photo_frame':frame})
    messages=c.build(obs(2),{})
    result=json.loads(next(m['content'] for m in messages if m['role']=='tool'))
    assert result['photo_frame']==frame
    state=json.loads(messages[-1]['content'][0]['text'])
    assert next(p for p in state['image_catalog'] if p['id']==crop['id'])['resolution']==frame['resolution']


def test_frame_ratio_mismatch_and_unrepresentable_ratio_preserve_state(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    initial=a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3'},obs())
    with pytest.raises(ValueError,match='frame_aspect_ratio_mismatch'):
        a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3',
                                 'rectangle':{'left':0,'top':0,'width':8,'height':8}},obs())
    with pytest.raises(ValueError,match='aspect_ratio_does_not_fit_source'):
        a.configure_photo_frame({'mode':'set','aspect_ratio':'17:13'},obs())
    assert a.photo_frame==initial


def test_maximum_frame_can_shift_and_reset_without_resolution_downgrade(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    rectangle={'left':0,'top':0,'width':8,'height':12}
    shifted=a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3','rectangle':rectangle},obs())
    assert shifted['rectangle']==rectangle
    assert shifted['resolution']['degraded'] is False
    assert shifted['resolution']['degradation_reason'] is None
    centered=a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3'},obs())
    assert centered['rectangle']==rectangle | {'left':4}
    assert centered['version']==2


def test_post_capture_crop_cannot_silently_bypass_resolution_policy(tmp_path):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'));a.capture(obs())
    args={'source_id':'shot_000001','left':3,'top':2,'width':6,'height':9}
    with pytest.raises(ValueError,match='resolution_downgrade_requires_reason'):
        a.crop_photo(args)
    assert a.crops==[]
    maximum=a.crop_photo(args | {'left':4,'top':0,'width':8,'height':12})
    assert maximum['resolution']['retained_max_frame_fraction']==1
    smaller=a.crop_photo(args | {'degradation_reason':'Remove an edge distraction after landing.'})
    assert smaller['resolution']['degraded'] is True


@pytest.mark.parametrize('arguments',[
    {'mode':'set','aspect_ratio':'0:3'}, {'mode':'set','aspect_ratio':'2.0:3'},
    {'mode':'set','aspect_ratio':None}, {'mode':'set','aspect_ratio':'2:3','rectangle':None},
    {'mode':'set','aspect_ratio':'2:3','degradation_reason':None},
    {'mode':'set','aspect_ratio':'2:3','degradation_reason':'   '},
    {'mode':'clear','aspect_ratio':'2:3'}, {'mode':'clear','degradation_reason':'budget'},
])
def test_framing_contract_rejects_ambiguous_arguments(arguments):
    with pytest.raises(ValueError):parse_tool_decision(reply('photo_frame',arguments))


def test_review_can_compare_source_and_reference_then_live_frame_returns(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    reference=reference_fixture(a)
    a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3'},obs(2))
    shot=a.capture(obs(2));crop=a.images[shot['framed_photo_id']]
    c=ContextBuilder(a,'2:3 portrait')
    c.request_photo_comparison(crop,'frame_000003')
    reviewing=c.build(obs(3),{},pending_review_id=crop['id'])
    assert {p['id'] for p in labels(reviewing)}=={'frame_000003',crop['id'],shot['id'],reference['id']}
    assert len(images(reviewing))==4
    c.request_images([shot['id'],crop['id']],'frame_000003')
    composing=c.build(obs(4),{})
    assert {'navigation','reference','capture','crop'}=={p['kind'] for p in labels(composing)}
    assert len(images(composing))==4


def test_agent_composes_inside_persistent_maximum_frame_before_capture(tmp_path):
    config,a,b,r=setup(tmp_path)
    def compose(messages):
        state=json.loads(messages[-1]['content'][0]['text'])
        assert state['photo_frame']['rectangle']=={'left':4,'top':0,'width':8,'height':12}
        assert labels(messages)[0]['viewfinder']['crop_box_px']==state['photo_frame']['rectangle']
        return reply('act',{'kind':'forward','value':20},
                     frame=state['current']['frame_id'],call_id='compose')
    policy=Policy([('photo_frame',{'mode':'set','aspect_ratio':'2:3'}),
                   ('act',{'kind':'takeoff'}),compose,('capture',{}),
                   ('review_photo',review_arguments('crop_000001')),
                   ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed'
    assert b.sent==['takeoff','forward','land']
    assert result['selected_photo']['resolution']['retained_max_frame_fraction']==1
    assert result['selected_photo']['frame_version']==1
    assert result['landing']['source']=='model'


def test_agent_can_correct_rejected_downsize_and_delivery_reports_resolution(tmp_path):
    from drone_agent.evaluation import evaluate_run
    config,a,b,r=setup(tmp_path)
    smaller={'mode':'set','aspect_ratio':'2:3',
             'rectangle':{'left':3,'top':2,'width':6,'height':9}}
    def correct(messages):
        rejection=json.loads(next(m['content'] for m in reversed(messages) if m['role']=='tool'))
        assert rejection['status']=='rejected'
        assert rejection['reason']=='maximum_native_frame_required'
        assert a.photo_frame['version']==0 and a.photo_frame['aspect_ratio']=='16:9'
        assert a.frame_contract is None
        state=json.loads(messages[-1]['content'][0]['text'])
        return reply('photo_frame',{'mode':'set','aspect_ratio':'2:3'},
                     frame=state['current']['frame_id'],call_id='correct')
    policy=Policy([('photo_frame',smaller),correct,('capture',{}),
                   ('review_photo',review_arguments('crop_000001')),
                   ('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed' and b.sent==[]
    report=evaluate_run(a.directory)
    assert report['delivery']['resolution']['retained_max_frame_fraction']==1
    assert 'retained_max_frame_fraction' in (a.directory/'report.html').read_text()
