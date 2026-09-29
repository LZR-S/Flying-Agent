import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from drone_agent.protocol import Action, Config, tool_definitions
from drone_agent.webots_backend import CommandState
from backends import FakeFlight


@pytest.mark.parametrize('kind,value,wire', [
    ('forward',20,'forward 20'),('back',500,'back 500'),
    ('left',40,'left 40'),('right',40,'right 40'),('up',20,'up 20'),('down',20,'down 20'),
    ('cw',360,'cw 360'),('ccw',1,'ccw 1'),('speed',10,'speed 10'),
    ('takeoff',0,'takeoff'),('land',0,'land'),('stop',0,'stop'),('hold',2,None),
])
def test_action_maps_exactly_to_one_sdk_command(kind,value,wire):
    assert Action(kind=kind,value=value).sdk_command()==wire


@pytest.mark.parametrize('kind,value', [
    ('forward',.4),('forward',20.5),('forward',20.),('forward',19),('forward',501),
    ('cw',.5),('ccw',361),('speed',9),('speed',101),('speed',True),('takeoff',1),
    ('rotate_cw',90),
])
def test_ambiguous_units_or_unsupported_sdk_values_are_rejected(kind,value):
    with pytest.raises(ValidationError):Action(kind=kind,value=value)


def flight():
    """A flight controller that reports every target as reached."""
    f=FakeFlight(position=(0.,0.,1.),yaw=0.)
    f.reached=True
    return f


def test_distance_is_cm_and_reference_moves_at_configured_sdk_speed():
    f=flight()
    c=CommandState(f,Action(kind='forward',value=100),'a',speed_cm_s=50)
    assert f.target_xy==(0.,0.)
    f.elapsed_s=1.
    assert c.poll() is None
    assert f.target_xy==pytest.approx((0.,.5))
    f.elapsed_s=2.
    assert c.poll() is None
    f.elapsed_s=2.6
    assert c.poll().status=='completed'
    assert f.target_xy==pytest.approx((0.,1.))


def test_down_does_not_silently_shorten_the_requested_distance():
    f=flight()
    c=CommandState(f,Action(kind='down',value=200),'a',speed_cm_s=100)
    f.elapsed_s=2.
    c.poll()
    assert f.target_altitude==pytest.approx(-1.)


def test_sdk_only_specifies_auto_takeoff_height_is_explicit_simulator_setting():
    f=flight()
    c=CommandState(f,Action(kind='takeoff'),'a',takeoff_height_m=.9)
    f.elapsed_s=3.
    c.poll()
    assert f.target_altitude==.9


def test_worlds_and_model_prompt_use_same_video_dimensions():
    from drone_agent.context import SYSTEM
    root=Path(__file__).resolve().parents[1]
    for path in (root/'webots/worlds').glob('*.wbt'):
        assert 'width 960' in path.read_text()
        assert 'height 720' in path.read_text()
    assert '960x720' in SYSTEM
    assert '1280x720' not in json.dumps(tool_definitions())
    assert Config().video_width==960
    assert Config().video_height==720


def test_profile_contains_valid_sdk_and_explicit_simulation_defaults():
    config=Config()
    assert config.control_profile=='tello-sdk-2-basic'
    assert 10<=config.speed_cm_s<=100
    assert config.keepalive_interval_s<15
    assert config.command_gap_s>=.1
    with pytest.raises(ValidationError):Config(speed_cm_s=101)
    with pytest.raises(ValidationError):Config(keepalive_interval_s=15.)


def test_runtime_keeps_idle_airborne_session_alive_without_counting_flight(tmp_path):
    from drone_agent.artifacts import Artifacts
    from drone_agent.runtime import Runtime,MissionEnd
    from test_loop_runtime import Backend
    now=[10.]
    b=Backend();b.airborne=True;b.keepalives=0
    def keepalive():b.keepalives+=1;return True
    b.keepalive=keepalive
    r=Runtime(b,Config(),Artifacts(tmp_path/'run',Config()),clock=lambda:now[0])
    now[0]=16.
    r.service()
    assert b.keepalives==1
    assert r.requests==0
    now[0]=32.
    with pytest.raises(MissionEnd,match='sdk_idle_timeout'):r.service()


def test_completed_result_does_not_claim_measured_position_precision():
    help=next(t['description'] for t in tool_definitions() if t['name']=='act')
    assert 'acknowledged' in help
    assert 'confirms controller tolerance' not in help


def test_long_hold_can_receive_keepalive_but_motion_cannot():
    from drone_agent.webots_backend import WebotsBackend
    backend=WebotsBackend.__new__(WebotsBackend)
    backend.connected=True
    backend.active=SimpleNamespace(action=Action(kind='hold',value=30))
    assert backend.keepalive()
    backend.active=SimpleNamespace(action=Action(kind='forward',value=20))
    assert not backend.keepalive()


def test_wire_schema_and_validation_both_require_distances():
    with pytest.raises(ValidationError):Action(kind='hold')
    schema=Action.model_json_schema()
    forward=next(x for x in schema['oneOf'] if x['properties']['kind']['const']=='forward')
    assert forward['properties']['value']=={'type':'integer','minimum':20,'maximum':500}
    assert 'value' in forward['required']


def test_thirty_second_hold_sends_keepalive_without_extra_motion(tmp_path):
    from drone_agent.artifacts import Artifacts
    from drone_agent.runtime import Runtime
    from drone_agent.protocol import ActionResult
    from test_loop_runtime import Backend
    now=[0.]
    b=Backend();b.airborne=True
    original_observe=b.observe
    b.observe=lambda:original_observe().model_copy(update={'received_at':now[0]})
    def tick():now[0]+=1
    b.tick=tick
    b.poll=lambda:ActionResult(action_id='hold',status='completed') if now[0]>=30 else None
    heartbeats=[]
    b.keepalive=lambda:heartbeats.append(now[0]) or True
    r=Runtime(b,Config(),Artifacts(tmp_path/'run',Config()),clock=lambda:now[0])
    result=r.execute(Action(kind='hold',value=30),'hold','frame_000001')
    assert result.status=='completed'
    assert heartbeats==[5.,10.,15.,20.,25.]
    assert b.sent==['hold']


def test_forward_motion_never_gets_zero_rc_interleaved(tmp_path):
    from drone_agent.artifacts import Artifacts
    from drone_agent.runtime import Runtime
    from drone_agent.protocol import ActionResult
    from test_loop_runtime import Backend
    now=[0.]
    b=Backend();b.airborne=True
    original_observe=b.observe
    b.observe=lambda:original_observe().model_copy(update={'received_at':now[0]})
    def tick():now[0]+=1
    b.tick=tick
    b.poll=lambda:ActionResult(action_id='move',status='completed') if now[0]>=20 else None
    b.keepalive=lambda:pytest.fail('zero RC must not interrupt active SDK movement')
    r=Runtime(b,Config(),Artifacts(tmp_path/'run',Config()),clock=lambda:now[0])
    assert r.execute(Action(kind='forward',value=500),'move','frame_000001').status=='completed'


def test_sdk_speed_changes_subsequent_command_reference():
    from drone_agent.webots_backend import WebotsBackend
    backend=WebotsBackend.__new__(WebotsBackend)
    backend.config=Config();backend.active=None;backend.speed_cm_s=50;backend.flight=flight()
    backend.begin(Action(kind='speed',value=25),'speed')
    assert backend.active.poll().status=='completed'
    backend.active=None
    backend.begin(Action(kind='forward',value=100),'move')
    assert backend.active.reference_duration==4.


def test_initial_requested_speed_is_visible_without_measured_telemetry(tmp_path):
    from drone_agent.context import ContextBuilder
    from drone_agent.artifacts import Artifacts
    from test_protocol_context import obs
    c=ContextBuilder(Artifacts(tmp_path/'run',Config()),'test',initial_speed_cm_s=30)
    data=json.loads(c.build(obs(),{})[-1]['content'][0]['text'])
    assert data['control_settings']['initial_speed_cm_s']==30
    assert data['control_settings']['translation_unit']=='cm'
    assert 'height_m' not in data['control_settings']
