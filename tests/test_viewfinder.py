import base64
import json
from types import MethodType

import cv2
import numpy as np
import pytest

from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from drone_agent.flight import RotorFlightController
from drone_agent.protocol import Action, Config, parse_tool_decision
from drone_agent.webots_backend import CommandState
from backends import FakeFlight
from native_helpers import reply
from test_cropping import labels
from test_protocol_context import obs, images


def exposure(seq=1):
    pixels=np.full((720,960,3),(30,80,130),dtype=np.uint8)
    pixels[200:400,400:600]=(90,110,170)
    ok,png=cv2.imencode('.png',pixels)
    assert ok
    return obs(seq).model_copy(update={'image_png':png.tobytes()})


def decode_input(part):
    return cv2.imdecode(np.frombuffer(base64.b64decode(part['image_url']['url'].split(',',1)[1]),np.uint8),cv2.IMREAD_COLOR)


def test_default_viewfinder_is_maximum_16_9_and_explicit_ratio_can_replace_it(tmp_path):
    a=Artifacts(tmp_path,Config());c=ContextBuilder(a,'拍一张2:3竖幅照片')
    m=c.build(exposure(),{})
    assert a.photo_frame['rectangle']=={'left':0,'top':90,'width':960,'height':540}
    assert a.frame_contract is None
    assert len(images(m))==1
    assert labels(m)[0]['viewfinder']['source_frame_id']=='frame_000001'
    a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3'},exposure())
    assert a.photo_frame['rectangle']=={'left':240,'top':0,'width':480,'height':720}
    assert a.frame_contract=={'width_px':480,'height_px':720,'aspect_ratio':'2:3'}


def test_default_capture_binds_ratio_and_contains_no_overlay_pixels(tmp_path):
    a=Artifacts(tmp_path,Config());c=ContextBuilder(a,'拍照');o=exposure()
    m=c.build(o,{})
    sent=decode_input(images(m)[0])
    original=cv2.imdecode(np.frombuffer(o.image_png,np.uint8),cv2.IMREAD_COLOR)
    assert not np.array_equal(sent,original)
    shot=a.capture(o);crop=a.images[shot['framed_photo_id']]
    np.testing.assert_array_equal(cv2.imread(str(a.image(crop['id']))),original[90:630,:])
    assert a.image(shot['id']).read_bytes()==o.image_png
    assert a.frame_contract=={'width_px':960,'height_px':540,'aspect_ratio':'16:9'}


def test_grid_switch_changes_only_annotation_and_preserves_rectangle(tmp_path):
    a=Artifacts(tmp_path,Config());o=exposure();c=ContextBuilder(a,'test')
    a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3',
                            'rectangle':{'left':120,'top':0,'width':480,'height':720},'guides':'thirds'},o)
    first=c.build(o,{})
    first_image=decode_input(images(first)[0])
    a.configure_photo_frame({'mode':'guides','guides':'golden'},o)
    second=c.build(o,{})
    second_image=decode_input(images(second)[0])
    assert a.photo_frame['rectangle']=={'left':120,'top':0,'width':480,'height':720}
    assert labels(second)[0]['viewfinder']['guides']=='golden'
    assert labels(first)[0]['viewfinder']['id']!=labels(second)[0]['viewfinder']['id']
    assert not np.array_equal(first_image,second_image)
    for messages in (first,second):
        record=a.images[labels(messages)[0]['viewfinder']['id']]
        annotated=cv2.imread(str(a.image(record['id'])))
        original=cv2.imdecode(np.frombuffer(o.image_png,np.uint8),cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(annotated[:,:119],original[:,:119])
        np.testing.assert_array_equal(annotated[:,601:],original[:,601:])
    assert a.image(o.frame_id).read_bytes()==o.image_png


def test_overlay_never_aliases_clean_photo_and_review_sees_clean_pixels(tmp_path):
    a=Artifacts(tmp_path,Config());o=exposure();c=ContextBuilder(a,'test')
    a.configure_photo_frame({'mode':'set','aspect_ratio':'4:3','guides':'thirds'},o)
    shot=a.capture(o);crop=a.images[shot['framed_photo_id']]
    c.request_photo_comparison(crop,o.frame_id)
    m=c.build(o,{},pending_review_id=crop['id'])
    shown=labels(m)
    assert shown[0]['image_id']==o.frame_id and shown[0]['viewfinder']
    assert 'aliases' not in next(p for p in m[-1]['content'] if p['type']=='text' and json.loads(p['text']).get('image_id')==o.frame_id)['text']
    assert crop['id'] in c.visible_images
    assert len(images(m))==2
    raw=cv2.imdecode(np.frombuffer(o.image_png,np.uint8),cv2.IMREAD_COLOR)
    ok,jpeg=cv2.imencode('.jpg',raw,[cv2.IMWRITE_JPEG_QUALITY,95]);assert ok
    assert base64.b64decode(images(m)[1]['image_url']['url'].split(',',1)[1])==jpeg.tobytes()


@pytest.mark.parametrize('history',[True,False])
def test_viewfinder_uses_one_slot_and_keeps_history_ablation(tmp_path,history):
    a=Artifacts(tmp_path,Config());c=ContextBuilder(a,'test',navigation_history=history)
    c.record_round_end(1,exposure(1));c.record_round_end(2,exposure(2))
    m=c.build(exposure(3),{})
    shown=labels(m)
    assert shown[0].get('viewfinder')
    assert all(p['kind']!='preview' for p in shown)
    assert {p['image_id'] for p in shown}==({'frame_000001','frame_000002','frame_000003'} if history else {'frame_000003'})
    assert all('viewfinder' not in p for p in shown[1:])


@pytest.mark.parametrize('args',[
    {'mode':'guides'}, {'mode':'guides','guides':'bad'},
    {'mode':'guides','guides':'thirds','aspect_ratio':'2:3'},
    {'mode':'clear','guides':'thirds'}, {'mode':'set','aspect_ratio':'2:3','guides':None},
])
def test_invalid_guides_do_not_enter_dispatch(args):
    with pytest.raises(ValueError):parse_tool_decision(reply('photo_frame',args))


def flight_command():
    f=FakeFlight(position=(0.,0.,1.))
    f.linear_reached=MethodType(RotorFlightController.linear_reached,f)
    return f,CommandState(f,Action(kind='up',value=20),'small-rise')


def test_twenty_cm_motion_does_not_complete_after_five_cm():
    f,command=flight_command();f.elapsed_s=1.2;f.position=(0.,0.,1.051);f.altitude_m=1.051
    f.velocity=(0.,0.,.10)
    assert command.poll() is None


def test_motion_requires_continuous_low_speed_settling_and_resets_on_drift():
    f,command=flight_command();f.elapsed_s=2.;f.position=(0.,0.,1.199);f.velocity=(0.,0.,.08)
    assert command.poll() is None
    f.velocity=(0.,0.,.01);f.elapsed_s=2.1
    assert command.poll() is None
    f.elapsed_s=2.4;f.position=(0.,0.,1.12)
    assert command.poll() is None
    f.elapsed_s=3.;f.position=(0.,0.,1.199)
    assert command.poll() is None
    f.elapsed_s=3.3
    assert command.poll() is None
    f.elapsed_s=3.6
    assert command.poll().status=='completed'


def test_unsettled_motion_times_out_without_false_completion():
    f,command=flight_command();f.elapsed_s=61.;f.position=(0.,0.,1.19);f.velocity=(0.,0.,.1)
    assert command.poll().status=='unknown'


def test_default_framed_capture_is_reviewed_and_delivered_in_agent_loop(tmp_path):
    from drone_agent.agent import AgentLoop
    from native_helpers import review_arguments
    from test_loop_runtime import Policy,setup
    config,a,b,r=setup(tmp_path)
    policy=Policy([('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',review_arguments('crop_000001')),
                   ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed'
    assert result['selected_photo']['aspect_ratio']=='16:9'
    assert a.frame_contract=={'width_px':16,'height_px':9,'aspect_ratio':'16:9'}
    assert len(a.shots)==len(a.crops)==1 and a.manual_crop_count==0


def test_guide_geometry_is_inside_shifted_frame_and_none_removes_only_grid(tmp_path):
    a=Artifacts(tmp_path,Config());o=exposure()
    a.configure_photo_frame({'mode':'set','aspect_ratio':'2:3','guides':'thirds',
                            'rectangle':{'left':120,'top':0,'width':480,'height':720}},o)
    first=a.viewfinder(o);grid=cv2.imread(str(a.image(first['id'])))
    a.configure_photo_frame({'mode':'guides','guides':'none'},o)
    second=a.viewfinder(o);border=cv2.imread(str(a.image(second['id'])))
    original=cv2.imdecode(np.frombuffer(o.image_png,np.uint8),cv2.IMREAD_COLOR)
    assert not np.array_equal(grid[100:200,279:283],original[100:200,279:283])
    np.testing.assert_array_equal(border[100:200,279:283],original[100:200,279:283])
    assert not np.array_equal(border[:,120:123],original[:,120:123])
    np.testing.assert_array_equal(border[:,:120],original[:,:120])


def test_settling_does_not_override_elapsed_command_deadline():
    f,command=flight_command();f.elapsed_s=59.8;f.position=(0.,0.,1.199);f.velocity=(0.,0.,0.)
    assert command.poll() is None
    f.elapsed_s=60.4
    assert command.poll().status=='unknown'


def test_audit_detects_changed_viewfinder_evidence(tmp_path):
    from drone_agent.audit import audit_requests
    from drone_agent.artifacts import write_json
    a=Artifacts(tmp_path,Config());c=ContextBuilder(a,'test');m=c.build(exposure(),{})
    write_json(tmp_path/'api/call_000001.request.json',{'messages':m})
    assert audit_requests(tmp_path)['status']=='passed'
    record=a.images[labels(m)[0]['viewfinder']['id']]
    a.image(record['id']).write_bytes(b'changed overlay')
    assert audit_requests(tmp_path)['status']=='failed'


@pytest.mark.parametrize('rectangle,axis', [
    ({'left':240,'top':0,'width':480,'height':720}, 'vertical'),
    ({'left':0,'top':90,'width':960,'height':540}, 'horizontal'),
])
def test_maximum_frame_only_marks_interior_crop_boundaries(rectangle, axis):
    from drone_agent.viewfinder import render_viewfinder
    raw=np.full((720,960,3),80,dtype=np.uint8)
    rendered=render_viewfinder(raw,{'rectangle':rectangle,'guides':'none'})
    if axis=='vertical':
        np.testing.assert_array_equal(rendered[:,245:715],raw[:,245:715])
        assert not np.array_equal(rendered[:,240:244],raw[:,240:244])
    else:
        np.testing.assert_array_equal(rendered[95:625,:],raw[95:625,:])
        assert not np.array_equal(rendered[90:94,:],raw[90:94,:])


def test_full_sensor_frame_needs_no_redundant_outline():
    from drone_agent.viewfinder import render_viewfinder
    raw=np.full((720,960,3),80,dtype=np.uint8)
    rendered=render_viewfinder(raw,{'rectangle':{'left':0,'top':0,'width':960,'height':720},'guides':'none'})
    np.testing.assert_array_equal(rendered,raw)


def test_guides_are_translucent_neutral_and_do_not_hide_scene_pixels():
    from drone_agent.viewfinder import render_viewfinder
    raw=np.full((720,960,3),80,dtype=np.uint8)
    rendered=render_viewfinder(raw,{'rectangle':{'left':240,'top':0,'width':480,'height':720},'guides':'thirds'})
    assert (rendered[:,:,0]==rendered[:,:,1]).all()
    assert (rendered[:,:,1]==rendered[:,:,2]).all()
    assert rendered.min()>=80 and rendered.max()<230
    np.testing.assert_array_equal(raw,np.full_like(raw,80))
    np.testing.assert_array_equal(rendered[:,:240],raw[:,:240])
    np.testing.assert_array_equal(rendered[:,720:],raw[:,720:])
