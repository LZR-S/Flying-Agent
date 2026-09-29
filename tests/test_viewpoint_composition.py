import json

import pytest

from drone_agent.agent import AgentLoop
from drone_agent.artifacts import Artifacts
from drone_agent.context import ContextBuilder
from drone_agent.protocol import Action, Config
from native_helpers import reply, review_arguments
from test_cropping import labels
from test_loop_runtime import Policy, setup
from test_protocol_context import images, obs


FRAME={'mode':'set','aspect_ratio':'2:3'}
SMALL={'left':3,'top':2,'width':6,'height':9}


def rejected_results(a):
    return [e['data'] for e in map(json.loads,a.trace.read_text().splitlines())
            if e['event']=='tool_result' and e['data']['status']=='rejected']


@pytest.mark.parametrize('reason',[None,'Crop tighter to satisfy the requested composition.'])
def test_default_policy_rejects_smaller_frame_and_crop_even_with_reason(tmp_path,reason):
    a=Artifacts(tmp_path/'run',Config())
    initial=a.configure_photo_frame(FRAME,obs())
    shot=a.capture(obs())
    extra={} if reason is None else {'degradation_reason':reason}
    with pytest.raises(ValueError,match='maximum_native_frame_required'):
        a.configure_photo_frame(FRAME | {'rectangle':SMALL} | extra,obs())
    with pytest.raises(ValueError,match='maximum_native_frame_required'):
        a.crop_photo({'source_id':shot['id']} | SMALL | extra)
    assert a.photo_frame==initial and len(a.crops)==1
    c=ContextBuilder(a,'portrait');state=json.loads(c.build(obs(2),{})[-1]['content'][0]['text'])
    assert state['framing_policy']=='max_native'
    assert state['frame_contract']=={'aspect_ratio':'2:3','width_px':8,'height_px':12}


@pytest.mark.parametrize('tool,arguments',[
    ('photo_frame',{'mode':'clear'}),
    ('photo_frame',{'mode':'set','aspect_ratio':'1:1'}),
    ('crop_photo',{'source_id':'shot_000001','left':0,'top':0,'width':12,'height':12}),
])
def test_frame_contract_cannot_be_cleared_or_bypassed_by_ratio_change(tmp_path,tool,arguments):
    config,a,b,r=setup(tmp_path)
    policy=Policy([('photo_frame',FRAME),('capture',{}),('review_photo',review_arguments('crop_000001')),
                   (tool,arguments),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed'
    assert len(rejected_results(a))==1
    assert rejected_results(a)[0]['reason']=='frame_contract_locked'
    assert a.photo_frame['aspect_ratio']=='2:3' and a.photo_frame['version']==1
    assert len(a.crops)==1


def test_first_manual_crop_also_locks_maximum_output_ratio(tmp_path):
    a=Artifacts(tmp_path/'run',Config());a.capture(obs())
    a.crop_photo({'source_id':'shot_000001','left':4,'top':0,'width':8,'height':12})
    with pytest.raises(ValueError,match='frame_contract_locked'):
        a.configure_photo_frame({'mode':'set','aspect_ratio':'1:1'},obs())


def test_finish_cannot_select_original_with_wrong_locked_ratio(tmp_path):
    config,a,b,r=setup(tmp_path)
    policy=Policy([('photo_frame',FRAME),('capture',{}),('review_photo',review_arguments('crop_000001')),
                   ('view_images',{'image_ids':['shot_000001']}),('review_photo',review_arguments()),
                   ('finish',{'shot_id':'shot_000001'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['selected_id']=='crop_000001'
    assert rejected_results(a)[0]['reason']=='delivery_frame_mismatch'


@pytest.mark.parametrize('history',[True,False])
def test_unresolved_composition_survives_motion_until_fresh_capture_review(tmp_path,history):
    config,a,b,r=setup(tmp_path,navigation_history=history)
    failed=review_arguments('crop_000001','unsatisfied') | {'next_step':'continue'}
    before=[]
    def move(messages):
        state=json.loads(messages[-1]['content'][0]['text'])
        feedback=state['composition_feedback']
        assert feedback['image_id']=='crop_000001'
        assert feedback['checks']==failed['checks']
        before.append(state['current']['frame_id'])
        return reply('act',{'kind':'up','value':20},frame=before[-1],call_id='adjust')
    def capture(messages):
        state=json.loads(messages[-1]['content'][0]['text'])
        assert state['composition_feedback']['checks']==failed['checks']
        assert state['motion_context']['capture_after_last_motion_required'] is True
        assert state['motion_context']['last_motion']['kind']=='up'
        shown=labels(messages)
        assert shown[0]['viewfinder']['source_frame_id']==state['current']['frame_id']
        assert (before[-1] in {p['id'] for p in shown})==history
        assert len(images(messages))<=4
        return reply('capture',frame=state['current']['frame_id'],call_id='recapture')
    def finish(messages):
        state=json.loads(messages[-1]['content'][0]['text'])
        assert state['composition_feedback'] is None
        return reply('finish',{'shot_id':'crop_000002'},frame=state['current']['frame_id'],call_id='deliver')
    policy=Policy([('photo_frame',FRAME),('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',failed),move,capture,('review_photo',review_arguments('crop_000002')),
                   ('act',{'kind':'land'}),finish])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed'
    assert b.sent==['takeoff','up','land']
    assert a.shots[1]['motion_sequence']>a.shots[0]['motion_sequence']
    assert result['selected_photo']['motion_sequence']==a.shots[1]['motion_sequence']
    assert result['selected_photo']['resolution']['retained_max_frame_fraction']==1


@pytest.mark.parametrize('attempt',[
    ('crop_photo',{'source_id':'shot_000001','left':4,'top':0,'width':8,'height':12}),
    ('review_photo',review_arguments('crop_000001')),
])
def test_movement_cannot_turn_failed_old_exposure_into_success(tmp_path,attempt):
    config,a,b,r=setup(tmp_path)
    failed=review_arguments('crop_000001','unsatisfied') | {'next_step':'continue'}
    policy=Policy([('photo_frame',FRAME),('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',failed),('act',{'kind':'forward','value':20}),
                   ('view_images',{'image_ids':['crop_000001']}),attempt,
                   ('capture',{}),('review_photo',review_arguments('crop_000002')),
                   ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000002'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed' and len(a.shots)==2
    assert rejected_results(a)[0]['reason']=='fresh_capture_required'
    assert len(a.crops)==2


def test_unsatisfied_photo_can_still_be_delivered_honestly_when_stopping(tmp_path):
    config,a,b,r=setup(tmp_path,max_photos=1)
    failed=review_arguments('crop_000001','unsatisfied')
    policy=Policy([('photo_frame',FRAME),('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',failed | {'next_step':'continue'}),('act',{'kind':'forward','value':20}),
                   ('view_images',{'image_ids':['crop_000001']}),('review_photo',failed),
                   ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='partial' and result['landing']['source']=='model'
    assert len(a.shots)==1 and rejected_results(a)==[]


def test_previously_good_photo_remains_selectable_after_optional_movement(tmp_path):
    config,a,b,r=setup(tmp_path)
    policy=Policy([('photo_frame',FRAME),('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',review_arguments('crop_000001')),('act',{'kind':'left','value':20}),
                   ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed' and len(a.shots)==1


def test_cancel_during_improvement_still_recovers_without_rephotographing(tmp_path):
    config,a,b,r=setup(tmp_path)
    def cancel(messages):
        (a.directory/'stop.request').touch()
        return reply('act',{'kind':'forward','value':20},
                     frame=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id'],call_id='cancelled')
    policy=Policy([('photo_frame',FRAME),('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',review_arguments('crop_000001','unsatisfied') | {'next_step':'continue'}),cancel])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='aborted' and result['landing']['source']=='recovery'
    assert len(a.shots)==1 and b.sent==['takeoff','land']


def test_a_later_failed_review_overrides_an_earlier_good_assessment(tmp_path):
    config,a,b,r=setup(tmp_path)
    failed=review_arguments('crop_000001','unsatisfied') | {'next_step':'continue'}
    policy=Policy([('photo_frame',FRAME),('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',review_arguments('crop_000001')),
                   ('view_images',{'image_ids':['crop_000001']}),('review_photo',failed),
                   ('act',{'kind':'up','value':20}),('view_images',{'image_ids':['crop_000001']}),
                   ('review_photo',review_arguments('crop_000001')),
                   ('review_photo',failed | {'next_step':'finish'}),
                   ('act',{'kind':'land'}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='partial'
    assert [p['reason'] for p in rejected_results(a)]==['fresh_capture_required']


def test_rejected_actions_and_landing_do_not_invalidate_photo_evidence(tmp_path):
    config,a,b,r=setup(tmp_path)
    policy=Policy([('photo_frame',FRAME),('capture',{}),
                   ('review_photo',review_arguments('crop_000001')),
                   ('act',{'kind':'up','value':20}),('finish',{'shot_id':'crop_000001'})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='completed' and result['selected_photo']['motion_sequence']==0
    assert result['motion_context']['last_motion'] is None
    assert b.sent==[]


def test_reusing_an_old_exposure_does_not_count_as_a_post_motion_capture(tmp_path):
    a=Artifacts(tmp_path/'run',Config())
    a.configure_photo_frame(FRAME,obs());a.capture(obs())
    photo=a.images['crop_000001']
    a.review_photo(review_arguments(photo['id'],'unsatisfied'),{photo['id']:photo['sha256']},
                   tool_call_id='review',based_on_frame_id='frame_000001')
    a.record_motion('move',Action(kind='forward',value=20),'frame_000001','Improve subject scale.')
    a.capture(obs())
    repeated=a.images['crop_000002']
    assert repeated['motion_sequence']==0
    with pytest.raises(ValueError,match='fresh_capture_required'):
        a.review_photo(review_arguments(repeated['id']),{repeated['id']:repeated['sha256']},
                       tool_call_id='false-new-exposure',based_on_frame_id='frame_000001')
    assert a.motion_context()['capture_after_last_motion_required'] is True


def test_unknown_movement_enters_recovery_without_claiming_new_viewpoint(tmp_path):
    config,a,b,r=setup(tmp_path)
    def unknown(messages):
        b.fail=True
        return reply('act',{'kind':'forward','value':20},
                     frame=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id'],call_id='unknown')
    policy=Policy([('photo_frame',FRAME),('act',{'kind':'takeoff'}),('capture',{}),
                   ('review_photo',review_arguments('crop_000001','unsatisfied')),unknown])
    result=AgentLoop(r,policy,a,config).run()
    assert result['status']=='aborted' and result['reason']=='unknown_action'
    assert result['motion_context']['last_motion']['kind']=='takeoff'
    assert len(a.shots)==1 and b.sent==['takeoff','forward','land']


def test_framing_mode_is_an_operator_setting_not_a_model_tool_argument():
    from drone_agent.cli import parser
    from drone_agent.protocol import parse_tool_decision
    assert parser().parse_args(['run']).framing_policy=='max_native'
    assert parser().parse_args(['run','--framing-policy','flexible']).framing_policy=='flexible'
    with pytest.raises(ValueError):
        parse_tool_decision(reply('photo_frame',FRAME | {'framing_policy':'flexible'}))
