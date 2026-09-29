import json

import cv2
import numpy as np
import pytest

from drone_agent.agent import AgentLoop
from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from drone_agent.protocol import Config, parse_tool_decision
from native_helpers import reply, review_arguments
from test_loop_runtime import Policy, setup
from test_protocol_context import obs, images


def crop_arguments():
    return dict(source_id='shot_000001',left=3,top=2,width=6,height=9,
                degradation_reason='Remove an edge distraction, accepting reduced detail.')


def labels(messages):
    groups=[json.loads(part['text']) for part in messages[-1]['content']
            if part['type']=='text' and 'image_id' in json.loads(part['text'])]
    return [label for group in groups for label in [group,*group.get('aliases',[])]]


def test_crop_copies_exact_source_pixels_and_keeps_exposure_provenance(tmp_path):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    pixels=np.arange(12*16*3,dtype=np.uint16).reshape(12,16,3).astype(np.uint8)
    ok,png=cv2.imencode('.png',pixels)
    assert ok
    source=a.capture(obs().model_copy(update={'image_png':png.tobytes()}))
    photo=a.crop_photo(crop_arguments())
    assert photo['id']=='crop_000001'
    assert photo['kind']=='crop'
    assert photo['width_px']==6 and photo['height_px']==9
    assert photo['aspect_ratio']=='2:3'
    assert photo['source_shot_id']==source['id']
    assert photo['source_frame_id']=='frame_000001'
    assert photo['source_sha256']==source['sha256']
    assert photo['captured_at']==1.
    assert photo['created_at']>photo['captured_at']
    assert photo['crop_box_px']=={'left':3,'top':2,'width':6,'height':9}
    np.testing.assert_array_equal(cv2.imread(str(a.image(photo['id']))),pixels[2:11,3:9])
    assert a.image(source['id']).read_bytes()==png.tobytes()
    assert len(a.shots)==1 and len(a.crops)==1 and len(a.navigation)==1
    assert source['width_px']==16 and source['height_px']==12


@pytest.mark.parametrize('patch', [
    {'left':-1},{'top':1.5},{'width':0},{'height':True},
    {'source_id':'frame_000001'},{'source_id':'crop_000001'},
    {'source_id':'../../evaluation/truth.jsonl'}, {'resize':2},
])
def test_invalid_crop_arguments_are_rejected_before_dispatch(patch):
    arguments=crop_arguments() | patch
    with pytest.raises(ValueError):
        parse_tool_decision(reply('crop_photo',arguments))


def test_crop_is_selectable_in_native_protocol():
    _,decision=parse_tool_decision(reply('crop_photo',crop_arguments()))
    assert decision.tool=='crop_photo'
    _,decision=parse_tool_decision(reply('finish',{'shot_id':'crop_000001'}))
    assert decision.arguments['shot_id']=='crop_000001'


@pytest.mark.parametrize('patch,reason', [
    ({'left':12},'crop_out_of_bounds'),
    ({'top':8},'crop_out_of_bounds'),
    ({'source_id':'shot_000099'},'unknown_source_photo'),
])
def test_invalid_source_or_bounds_does_not_create_artifacts(tmp_path,patch,reason):
    a=Artifacts(tmp_path/'run',Config());a.capture(obs())
    before=set(a.images)
    with pytest.raises(ValueError,match=reason):a.crop_photo(crop_arguments() | patch)
    assert set(a.images)==before
    assert a.crops==[]


@pytest.mark.parametrize('navigation_history', [True,False])
def test_photo_comparison_preserves_crop_source_and_caps_images(tmp_path,navigation_history):
    a=Artifacts(tmp_path/'run',Config(framing_policy='flexible'))
    for seq in range(1,5):a.capture(obs(seq))
    crop=a.crop_photo(crop_arguments())
    c=ContextBuilder(a,'拍一张2:3竖幅全身照',navigation_history=navigation_history)
    c.record(reply('crop_photo',crop_arguments()),{'status':'completed','photo':crop})
    c.request_photo_comparison(crop,'frame_000004')
    messages=c.build(obs(5),{})
    shown=labels(messages)
    assert [p['image_id'] for p in shown]==['frame_000005','crop_000001','shot_000001','shot_000004']
    assert len(images(messages))==4
    assert shown[1]['captured_at']==1. and shown[1]['source_shot_id']=='shot_000001'
    assert shown[1]['source_tool_call_id']=='call_test'
    assert 'frame_000001' not in c.image_sources
    assert shown[1]['width_px']==6 and shown[1]['height_px']==9
    catalog=json.loads(messages[-1]['content'][0]['text'])['image_catalog']
    assert next(p for p in catalog if p['id']=='crop_000001')['aspect_ratio']=='2:3'
    c.request_images(['crop_000001'],'frame_000005')
    assert [p['image_id'] for p in labels(c.build(obs(6),{}))]==['frame_000006','crop_000001']


def test_second_capture_is_shown_with_first_candidate_without_extra_model_call(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    seen=[]
    def review(messages):
        seen.extend(labels(messages))
        frame=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply('review_photo',review_arguments('shot_000002'),frame=frame,call_id='review')
    result=AgentLoop(r,Policy([('capture',{}),('review_photo',review_arguments()),
                              ('capture',{}),review,('finish',{'shot_id':'shot_000002'})]),a,config).run()
    assert result['status']=='completed'
    assert {p['image_id'] for p in seen if p['kind']=='capture'}=={'shot_000001','shot_000002'}


def test_crop_can_be_reviewed_and_delivered_after_landing_without_new_exposure(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    policy=Policy([('act',{'kind':'takeoff'}),('capture',{}),('review_photo',review_arguments()),('act',{'kind':'land'}),
                   ('crop_photo',crop_arguments()),('view_images',{'image_ids':['shot_000001','crop_000001']}),
                   ('review_photo',review_arguments('crop_000001')),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed'
    assert result['selected_id']=='crop_000001'
    assert result['selected']=='crops/crop_000001.png'
    assert result['selected_photo']['source_shot_id']=='shot_000001'
    assert len(result['shots'])==1 and len(result['crops'])==1
    assert result['action_requests']==2
    assert b.sent==['takeoff','land']
    assert result['landing']['source']=='model'


def test_rejected_crop_does_not_terminate_or_consume_capture_budget(tmp_path):
    config,a,b,r=setup(tmp_path,framing_policy='flexible',max_photos=1,max_crops=1)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    policy=Policy([('capture',{}),('review_photo',review_arguments()),('crop_photo',crop_arguments() | {'left':16}),
                   ('crop_photo',crop_arguments()),('review_photo',review_arguments('crop_000001')),
                   ('crop_photo',crop_arguments()),
                   ('view_images',{'image_ids':['crop_000001']}),
                   ('review_photo',review_arguments('crop_000001')),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed'
    assert len(a.shots)==1 and len(a.crops)==1
    assert 'crop_out_of_bounds' in a.trace.read_text() and 'crop_budget' in a.trace.read_text()
    budgets=r.budgets(0,0,len(a.shots))
    assert budgets['remaining_photos']==0 and budgets['remaining_crops']==0


def test_crop_report_distinguishes_derivatives_from_exposures(tmp_path):
    from drone_agent.evaluation import evaluate_run
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    AgentLoop(r,Policy([('capture',{}),('review_photo',review_arguments()),('crop_photo',crop_arguments()),
                        ('review_photo',review_arguments('crop_000001')),('finish',{'shot_id':'crop_000001'})]),a,config).run()
    result=evaluate_run(a.directory)
    assert result['counts']['photos']==1 and result['counts']['crops']==1
    assert result['delivery']['kind']=='crop'
    assert result['delivery']['width_px']==6
    report=(a.directory/'report.html').read_text()
    assert 'crops/crop_000001.png' in report and 'shots/shot_000001.png' in report
    assert 'source_shot_id' in report and 'crop_box_px' in report
