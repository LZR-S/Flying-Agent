import hashlib
import json

import cv2
import numpy as np
import pytest

from drone_agent.agent import AgentLoop
from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from drone_agent.evaluation import evaluate_run
from drone_agent.protocol import Config, parse_tool_decision
from native_helpers import reply, review_arguments
from test_cropping import crop_arguments, labels
from test_loop_runtime import Policy, setup
from test_protocol_context import obs, images


BOX = {'left':3, 'top':2, 'width':6, 'height':9}


def test_frame_preview_follows_new_exposures_and_capture_preserves_both(tmp_path):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    setting=a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX},obs())
    assert setting['version']==1 and setting['rectangle']==BOX
    c=ContextBuilder(a,'test')
    first=c.build(obs(),{})
    first_preview=a.frame_preview(obs())
    assert labels(first)[0]['viewfinder']['source_frame_id']=='frame_000001'
    pixels=np.arange(12*16*3,dtype=np.uint16).reshape(12,16,3).astype(np.uint8)
    ok,png=cv2.imencode('.png',pixels);assert ok
    fresh=obs(2).model_copy(update={'image_png':png.tobytes()})
    second=c.build(fresh,{})
    preview=a.frame_preview(fresh)
    assert labels(second)[0]['viewfinder']['source_frame_id']=='frame_000002'
    assert preview['id']!=first_preview['id']
    assert preview['source_frame_id']=='frame_000002' and preview['frame_version']==1
    np.testing.assert_array_equal(cv2.imread(str(a.image(preview['id']))),pixels[2:11,3:9])
    assert preview['id'] not in c.visible_frames
    captured_pixels=255-pixels
    ok,capture_png=cv2.imencode('.png',captured_pixels);assert ok
    exposure=obs(3).model_copy(update={'image_png':capture_png.tobytes()})
    shot=a.capture(exposure)
    framed=a.images[shot['framed_photo_id']]
    assert framed['source_shot_id']==shot['id'] and framed['frame_version']==1
    assert framed['captured_at']==shot['captured_at']==3.
    assert framed['source_frame_id']!=preview['source_frame_id']
    assert framed['source_sha256']==hashlib.sha256(capture_png.tobytes()).hexdigest()
    assert a.image(shot['id']).read_bytes()==capture_png.tobytes()
    np.testing.assert_array_equal(cv2.imread(str(a.image(framed['id']))),captured_pixels[2:11,3:9])
    assert a.valid_review(framed['id']) is None
    a.configure_photo_frame({'mode':'clear'},obs())
    assert a.photo_frame=={'version':2,'rectangle':None}
    assert all(p['kind']!='preview' for p in labels(c.build(obs(4),{})))
    assert 'framed_photo_id' not in a.capture(obs(4))


def test_invalid_frame_is_rejected_without_changing_previous_setting(tmp_path):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX},obs())
    with pytest.raises(ValueError,match='crop_out_of_bounds'):
        a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX | {'left':15}},obs())
    assert a.photo_frame['version']==1 and a.photo_frame['rectangle']==BOX


@pytest.mark.parametrize('tool,args',[
    ('photo_frame',{}),
    ('photo_frame',{'mode':'set'}),
    ('photo_frame',{'mode':'clear','rectangle':None}),
    ('photo_frame',{'mode':'invalid'}),
    ('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX | {'height':0}}),
    ('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX | {'left':1.5}}),
    ('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':None}),
    ('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':json.dumps(BOX)}),
    ('photo_frame',{'mode':'clear','rectangle':BOX}),
    ('finish',{'shot_id':'preview_000001'}),
    ('review_photo',{'image_id':'preview_000001'}),
    ('review_photo',review_arguments() | {'checks':[]}),
    ('review_photo',review_arguments() | {'rationale':'  '}),
])
def test_frame_review_rejects_invalid_contract(tool,args):
    with pytest.raises(ValueError):parse_tool_decision(reply(tool,args))


def test_clear_frame_dispatch_restores_original_only_capture(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    p=Policy([('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX}),('photo_frame',{'mode':'clear'}),('capture',{}),
              ('review_photo',review_arguments()),('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed' and b.sent==[]
    assert len(a.shots)==1 and not a.crops
    assert a.photo_frame=={'version':2,'rectangle':None}


@pytest.mark.parametrize('arguments',[
    {'mode':'set'}, {'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':None},
    {'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':json.dumps(BOX)},
    {'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX | {'left':15}},
    {'mode':'clear','rectangle':BOX}, {'mode':'clear','rectangle':None},
])
def test_invalid_frame_call_preserves_previous_frame_and_explains_error(tmp_path,arguments):
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    p=Policy([('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX}),('photo_frame',arguments),
              ('finish',{'shot_id':None,'abandon':True})])
    result=AgentLoop(r,p,a,config).run()
    assert result['reason']=='agent_abandoned' and b.sent==[]
    assert a.photo_frame['version']==1 and a.photo_frame['rectangle']==BOX
    errors=[json.loads(line)['data'] for line in a.trace.read_text().splitlines()
            if json.loads(line)['event'] in ('protocol_error','tool_result')
            and json.loads(line)['data']['status']=='rejected']
    assert len(errors)==1
    if arguments=={'mode':'set'}:
        feedback=errors[0]['validation_errors'][0]
        assert feedback['location']==['aspect_ratio']
        assert 'required' in feedback['message'] and 'set' in feedback['message']
    if arguments=={'mode':'clear','rectangle':BOX}:
        assert 'Omit aspect_ratio, rectangle' in errors[0]['validation_errors'][0]['message']


@pytest.mark.parametrize('history',[True,False])
def test_live_frame_is_pinned_while_composing_and_ablation_is_complete(tmp_path,history):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX},obs())
    for n in range(1,4):a.capture(obs(n))
    c=ContextBuilder(a,'test',navigation_history=history)
    c.build(obs(4),{})
    preview=a.frame_preview(obs(4))
    c.record_round_end(1,obs(4))
    c.request_images(['shot_000001','shot_000002','shot_000003'],'frame_000004')
    messages=c.build(obs(5),{})
    assert [p['kind'] for p in labels(messages)]==['navigation','capture','capture','capture']
    assert [p['image_id'] for p in labels(messages) if p['kind']=='capture']==['shot_000001','shot_000002','shot_000003']
    assert len(images(messages))==4
    state=json.loads(messages[-1]['content'][0]['text'])
    assert state['omitted_requested_image_ids']==[]
    assert labels(messages)[0]['viewfinder']['source_frame_id']=='frame_000005'
    with pytest.raises(ValueError,match='preview_not_replayable'):
        c.request_images([preview['id']],'frame_000005')
    c.record_round_end(2,obs(5))
    shown=labels(c.build(obs(6),{}))
    assert all(p['kind']!='preview' for p in shown)
    assert shown[0]['viewfinder']['source_frame_id']=='frame_000006'
    assert len(shown)==(3 if history else 1)


def test_valid_review_survives_landing(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('act',{'kind':'takeoff'}),('capture',{}),('view_images',{'image_ids':['shot_000001']}),
              ('review_photo',review_arguments()),('act',{'kind':'land'}),('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed' and result['steps']==6
    assert result['selected_review']['image_sha256']==result['selected_photo']['sha256']
    assert result['selected_review']['fulfillment']=='satisfied'
    assert result['selected_review']['tool_call_id']=='call_4'
    assert result['landing']['source']=='model'


def test_invisible_image_review_is_rejected_and_requeued(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('capture',{}),('review_photo',review_arguments()),('photo_frame',{'mode':'clear'}),('review_photo',review_arguments()),
              ('review_photo',review_arguments()),('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed'
    assert 'review_image_not_visible' in a.trace.read_text()
    assert len(a.reviews)==2


def test_new_crop_needs_own_review_and_partial_delivery_is_explicit(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    partial=review_arguments('crop_000001',status='unknown')
    p=Policy([('capture',{}),('review_photo',review_arguments()),('crop_photo',crop_arguments()),
              ('finish',{'shot_id':'crop_000001'}),('review_photo',partial),
              ('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='partial' and result['agent_finished']
    assert result['selected_id']=='crop_000001' and len(a.reviews)==2
    assert result['selected_review']['fulfillment']=='unknown'
    report=evaluate_run(a.directory)
    assert report['agent_review']['fulfillment']=='unknown'
    assert report['photo_review']['status']=='pending_blind_review'
    assert report['counts']['photo_reviews']==2
    assert 'Agent self-review' in (a.directory/'report.html').read_text()


def test_continue_review_does_not_authorize_finish_or_restrict_movement(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('capture',{}),('review_photo',review_arguments() | {'next_step':'continue'}),
              ('finish',{'shot_id':'shot_000001'}),('act',{'kind':'takeoff'}),
              ('act',{'kind':'land'}),('view_images',{'image_ids':['shot_000001']}),
              ('review_photo',review_arguments()),('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed' and result['steps']==8
    assert 'review_not_final' in a.trace.read_text()


def test_review_rejects_pixels_changed_since_request_and_invalidates_changed_artifact(tmp_path):
    a=Artifacts(tmp_path/'run',Config());shot=a.capture(obs())
    c=ContextBuilder(a,'test');c.request_images([shot['id']],'frame_000001');c.build(obs(2),{})
    review=a.review_photo(review_arguments(),c.visible_images,tool_call_id='review',based_on_frame_id='frame_000002')
    assert a.valid_review(shot['id'])==review
    a.image(shot['id']).write_bytes(b'changed')
    assert a.valid_review(shot['id']) is None
    with pytest.raises(ValueError,match='image_evidence_changed'):
        a.review_photo(review_arguments(),c.visible_images,tool_call_id='again',based_on_frame_id='frame_000002')


def test_framed_capture_uses_photo_budget_and_manual_crops_keep_separate_budget(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible',max_photos=1,max_crops=0)
    p=Policy([('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':BOX}),('capture',{}),
              ('review_photo',review_arguments('crop_000001')),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed'
    assert result['action_requests']==0 and len(a.shots)==len(a.crops)==1
    assert result['selected_photo']['derivation']=='photo_frame'
    assert r.budgets(0,0,1)['remaining_crops']==0
    assert evaluate_run(a.directory)['counts']['framed_photos']==1
