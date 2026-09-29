import time
import pytest
from drone_agent.protocol import Action, ActionResult, Config, Decision
from drone_agent.artifacts import Artifacts
from drone_agent.runtime import Runtime, MissionEnd
from drone_agent.agent import AgentLoop
from test_protocol_context import obs
from native_helpers import reply, review_arguments
from backends import FakeBackend


class Backend(FakeBackend):
    """The default fake: one command in flight, completed on the next tick.

    `backends.FakeBackend` is the implementation; this name is what the other
    test modules import.
    """

    def __init__(self):
        super().__init__()


class Policy:
    attempts=0
    def __init__(self, actions): self.actions=iter(actions)
    def complete(self, messages):
        self.attempts+=1
        item=next(self.actions)
        if callable(item): return item(messages)
        # Use the actual current frame supplied in the request.
        import json
        current=json.loads(messages[-1]['content'][0]['text'])['current']['frame_id']
        return reply(item[0],item[1],frame=current,call_id=f'call_{self.attempts}')


def setup(tmp_path, **kwargs):
    config=Config(**kwargs); a=Artifacts(tmp_path/'run',config); b=Backend()
    return config,a,b,Runtime(b,config,a)


def test_duplicate_command_is_not_redispatched(tmp_path):
    _,a,b,r=setup(tmp_path)
    first=r.execute(Action(kind='takeoff',value=0), 'a', 'frame_000001')
    second=r.execute(Action(kind='takeoff',value=0), 'a', 'frame_000001')
    assert first==second
    assert b.sent==['takeoff']


def test_unknown_action_latches_movement_and_recovery_is_once(tmp_path):
    _,a,b,r=setup(tmp_path)
    r.execute(Action(kind='takeoff',value=0),'a','frame_000001')
    b.fail=True
    result=r.execute(Action(kind='forward',value=100),'b','frame_000001')
    assert result.status=='unknown'
    with pytest.raises(MissionEnd): r.execute(Action(kind='left',value=100),'c','frame_000001')
    b.fail=False
    r.recover(); r.recover()
    assert b.sent==['takeoff','forward','land']
    assert r.landing['source']=='recovery'


def test_agent_can_capture_improve_review_then_land_and_select(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('act',{'kind':'takeoff','value':0}),('capture',{}),
       ('review_photo',review_arguments() | {'next_step':'continue'}),
       ('act',{'kind':'left','value':20}),('capture',{}),
       ('view_images',{'image_ids':['shot_000001','shot_000002']}),
       ('review_photo',review_arguments('shot_000002')),
       ('act',{'kind':'land','value':0}),('finish',{'shot_id':'shot_000002'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed'
    assert result['selected_id']=='shot_000002'
    assert result['landing']['source']=='model'
    assert b.sent==['takeoff','left','land']
    assert len(a.shots)==2


def test_finish_airborne_is_recoverable_tool_error(tmp_path):
    config,a,b,r=setup(tmp_path)
    a.configure_photo_frame({'mode':'clear'},b.observe())  # Exercise explicit original-only capture.
    p=Policy([('act',{'kind':'takeoff','value':0}),('capture',{}),('review_photo',review_arguments()),
              ('finish',{'shot_id':'shot_000001'}),('act',{'kind':'land','value':0}),
              ('finish',{'shot_id':'shot_000001'})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='completed'
    assert 'landing_required' in a.trace.read_text()


def test_three_protocol_errors_stop_without_executing(tmp_path):
    config,a,b,r=setup(tmp_path)
    result=AgentLoop(r,Policy([lambda _:{}]*3),a,config).run()
    assert result['reason']=='protocol_error_limit'
    assert b.sent==[]


def test_round_end_history_includes_tool_and_protocol_rejections(tmp_path):
    import json
    config,a,b,r=setup(tmp_path)
    def finish(messages):
        labels=[json.loads(part['text']) for part in messages[-1]['content']
                if part['type']=='text' and 'image_id' in json.loads(part['text'])]
        assert [label['round_ends'][0]['round'] for label in labels[1:]]==[3,2]
        assert labels[1]['round_ends'][0]['tool_call_id'] is None
        assert labels[2]['round_ends'][0]['tool_call_id']=='call_2'
        for label in labels:
            assert a.image(label['image_id']).exists()
        return reply('finish',{'shot_id':None,'abandon':True},frame=labels[0]['image_id'],call_id='finish')
    policy=Policy([('photo_frame',{'mode':'clear'}),('act',{'kind':'forward','value':20}),lambda _: {},finish])
    result=AgentLoop(r,policy,a,config).run()
    assert result['reason']=='agent_abandoned' and b.sent==[]
    events=[json.loads(line) for line in a.trace.read_text().splitlines()]
    assert [e['data']['round'] for e in events if e['event']=='round_end']==[1,2,3,4]


def test_every_decision_gets_fresh_public_observation_without_observe_tool(tmp_path):
    import json
    config,a,b,r=setup(tmp_path,framing_policy='flexible')
    original=b.observe
    def observation():
        current=original()
        return current.model_copy(update={'battery_pct':100.-current.captured_at/10})
    b.observe=observation
    seen=[]
    class RecordingPolicy(Policy):
        def complete(self,messages):
            state=json.loads(messages[-1]['content'][0]['text'])
            seen.append(state)
            assert all(not isinstance(m.get('content'),list) for m in messages[:-1])
            labels=[json.loads(p['text']) for p in messages[-1]['content'] if p['type']=='text']
            current=next(label for label in labels if label.get('current') is True)
            assert current['image_id']==state['current']['frame_id']
            return super().complete(messages)
    policy=RecordingPolicy([
        ('act',{'kind':'takeoff'}),('act',{'kind':'forward','value':20}),
        ('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':{'left':15,'top':0,'width':6,'height':9}}),
        lambda _: {},
        ('photo_frame',{'mode':'set','aspect_ratio':'2:3','degradation_reason':'Accept less detail for the test crop.','rectangle':{'left':3,'top':2,'width':6,'height':9}}),
        ('photo_frame',{'mode':'clear'}),('act',{'kind':'hold','value':0}),
        ('act',{'kind':'land'}),('finish',{'shot_id':None,'abandon':True})])
    result=AgentLoop(r,policy,a,config).run()
    assert result['reason']=='agent_abandoned' and len(seen)==9
    assert b.sent==['takeoff','forward','hold','land']
    assert result['action_requests']==4
    assert [s['round'] for s in seen]==list(range(1,10))
    for n,state in enumerate(seen):
        current=state['current']
        assert set(current)=={'frame_id','captured_at','image_age_s','battery_pct','connected','airborne','landed'}
        assert current['connected'] and current['image_age_s']<config.max_image_age_s
        assert state['budgets']['remaining_steps']==config.max_steps-n
        assert state['budgets']['remaining_api_attempts']==config.max_api_attempts-n
        if n:
            assert current['captured_at']>seen[n-1]['current']['captured_at']
            assert current['battery_pct']<seen[n-1]['current']['battery_pct']
    assert not seen[0]['current']['airborne'] and seen[1]['current']['airborne']
    assert seen[-1]['current']['landed']
    assert seen[5]['photo_frame']['version']==1 and seen[6]['photo_frame']=={'version':2,'rectangle':None}
    assert 'crop_out_of_bounds' in a.trace.read_text() and 'protocol_error' in a.trace.read_text()


def test_stale_automatic_observation_prevents_model_call_and_recovers(tmp_path):
    config,a,b,r=setup(tmp_path)
    b.airborne=True
    original=b.observe
    b.observe=lambda:original().model_copy(update={'received_at':0.})
    policy=Policy([])
    result=AgentLoop(r,policy,a,config).run()
    assert result['reason']=='stale_image' and policy.attempts==0
    assert b.sent==['land'] and result['landing']['source']=='recovery'


def test_api_wait_services_flight_and_late_action_does_not_execute(tmp_path):
    config,a,b,r=setup(tmp_path,api_timeout_s=.02)
    b.airborne=True
    def slow(_):
        time.sleep(.08)
        return reply('act',{'kind':'forward','value':100})
    result=AgentLoop(r,Policy([slow]),a,config).run()
    assert result['reason']=='api_timeout'
    assert b.seq>3
    assert b.sent==['land']
    assert result['landing']['source']=='recovery'


def test_nonexistent_photo_is_rejected_not_selected(tmp_path):
    config,a,b,r=setup(tmp_path)
    p=Policy([('finish',{'shot_id':'shot_000099'}),('finish',{'shot_id':None,'abandon':True})])
    result=AgentLoop(r,p,a,config).run()
    assert result['status']=='incomplete'
    assert result['selected_id'] is None
    assert 'unknown_shot_id' in a.trace.read_text()


def test_duplicate_identity_with_different_action_is_rejected(tmp_path):
    _,a,b,r=setup(tmp_path)
    r.execute(Action(kind='takeoff',value=0), 'a', 'frame_000001')
    with pytest.raises(ValueError,match='action_id_conflict'):
        r.execute(Action(kind='forward',value=100), 'a', 'frame_000001')
    assert b.sent==['takeoff']


def test_reply_after_mission_deadline_cannot_execute(tmp_path):
    config,a,b,r=setup(tmp_path)
    def expired(messages):
        r.deadline=0
        return reply('act',{'kind':'takeoff','value':0},frame='frame_000002')
    result=AgentLoop(r,Policy([expired]),a,config).run()
    assert result['reason']=='mission_deadline'
    assert b.sent==[]


@pytest.mark.parametrize('fault,reason', [('cancel','operator_stop'),('stale','stale_image'),('battery','low_battery')])
def test_long_action_fault_interrupts_and_lands_once(tmp_path,fault,reason):
    config,a,b,r=setup(tmp_path)
    b.airborne=True
    base_tick=b.tick
    base_observe=b.observe
    b.poll=lambda: None
    def tick():
        base_tick()
        if b.active and b.active[1].kind=='forward':
            if fault=='cancel':(a.directory/'stop.request').touch()
            if fault=='stale':b.observe=lambda:base_observe().model_copy(update={'received_at':0.})
            if fault=='battery':b.observe=lambda:base_observe().model_copy(update={'battery_pct':10.})
    b.tick=tick
    with pytest.raises(MissionEnd,match=reason):
        r.execute(Action(kind='forward',value=100),'a','frame_000001')
    assert r.results['a'].status=='unknown'
    b.observe=base_observe;b.poll=lambda:ActionResult(action_id='recovery_land',status='completed')
    r.recover();r.recover()
    assert b.sent==['forward','land']
