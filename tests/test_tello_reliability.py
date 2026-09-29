"""Fault injection at the decoded-frame, telemetry and SDK wire boundaries."""
import time

import cv2
import numpy as np
import pytest

from backends import FakeTelloSdk
from drone_agent.artifacts import Artifacts
from drone_agent.protocol import Action, Config
from drone_agent.runtime import Runtime, MissionEnd
from drone_agent.tello_backend import TelloBackend


class Clock:
    def __init__(self): self.now = time.monotonic()
    def __call__(self): return self.now
    def advance(self, dt): self.now += dt


class WireSdk(FakeTelloSdk):
    """A receiver with explicit new samples, independent of getter calls."""
    def __init__(self, clock, *, ground=True):
        super().__init__(frame=np.full((720, 960, 3), [220, 50, 10], np.uint8),
                         height_cm=0 if ground else 150, tof_cm=5 if ground else 150)
        self.clock = clock
        self.retry_count = 3
        self.responses = []
        self.wire = []
        self.acks = True
        self.frame_seq = self.state_seq = 0
        self.publish_frame()
        self.publish_state()

    def publish_frame(self, pixels=None):
        if pixels is not None: self._reader.frame = pixels
        self.frame_seq += 1
        self.video = (self.frame_seq, self.clock(), time.time(), self._reader.frame.copy())

    def publish_state(self, **fields):
        self.state_seq += 1
        state = {'h': self.height_cm, 'tof': self.tof_cm, 'yaw': self.yaw_deg,
                 'bat': self.battery, 'vgx': 0, 'vgy': 0, 'vgz': 0, 'roll': 0, 'pitch': 0}
        state.update(fields)
        self.state = (self.state_seq, self.clock(), state)

    def frame_sample(self): return self.video
    def state_sample(self): return self.state
    def get_own_udp_object(self): return {'responses': self.responses}
    def set_speed(self, value): self.calls.append(('set_speed', value))
    def send_command_without_return(self, command):
        self.wire.append(command)
        if self.acks and not command.startswith('rc '): self.responses.append(b'ok')


def setup(tmp_path, **kwargs):
    clock = Clock()
    sdk = WireSdk(clock)
    config = Config(**kwargs)
    backend = TelloBackend(sdk, config, clock=clock)
    backend.connect()
    artifacts = Artifacts(tmp_path, config)
    return clock, sdk, backend, Runtime(backend, config, artifacts, clock=clock)


def test_changed_frame_can_be_archived_with_a_new_identity(tmp_path):
    _, sdk, b, r = setup(tmp_path)
    first = r.observe()
    sdk.publish_frame(np.zeros((720, 960, 3), np.uint8))
    second = r.observe()
    assert first.frame_id != second.frame_id
    assert len(r.artifacts.navigation) == 2


def test_frozen_frame_keeps_age_and_static_new_exposure_has_new_id(tmp_path):
    clock, sdk, b, r = setup(tmp_path)
    first = r.observe()
    clock.advance(.4)
    sdk.publish_state()
    assert b.observe().received_at == first.received_at
    sdk.publish_frame()
    second = b.observe()
    assert first.frame_id != second.frame_id and first.image_png == second.image_png
    clock.advance(1.)
    sdk.publish_state()
    with pytest.raises(MissionEnd, match='stale_image'): r.check()


def test_capture_waits_for_next_decoded_frame_without_fabricating_exposure(tmp_path):
    _, sdk, b, r = setup(tmp_path, max_image_age_s=.03)
    first = b.observe()
    with pytest.raises(Exception, match='fresh_frame_timeout'):
        b.capture()
    assert b.observe().frame_id == first.frame_id


def test_initial_speed_and_dynamic_speed_are_sent_once(tmp_path):
    _, sdk, b, r = setup(tmp_path, speed_cm_s=35)
    assert ('set_speed', 35) in sdk.calls
    b.begin(Action(kind='speed', value=25), 'speed')
    b.tick()
    assert b.poll().status == 'completed'
    assert sdk.wire == ['speed 25']
    assert b.speed_cm_s == 25


def test_speed_timeout_does_not_claim_new_setting(tmp_path):
    clock, sdk, b, _ = setup(tmp_path, command_timeout_s=.1)
    sdk.acks = False
    b.begin(Action(kind='speed', value=25), 'speed')
    clock.advance(.2); b.tick()
    assert b.poll().status == 'unknown'
    assert b.speed_cm_s == 50
    assert sdk.wire.count('speed 25') == 1


def test_takeoff_unknown_cannot_remain_landed(tmp_path):
    clock, sdk, b, r = setup(tmp_path, takeoff_timeout_s=.1)
    sdk.acks = False
    b.begin(Action(kind='takeoff'), 'takeoff')
    clock.advance(.2); b.tick()
    assert b.poll().status == 'unknown'
    assert not b.observe().landed
    b.stop_motion()
    b.begin(Action(kind='land'), 'recovery_land')
    assert sdk.wire.count('land') == 1


def test_late_ack_cannot_confirm_recovery_landing(tmp_path):
    clock, sdk, b, _ = setup(tmp_path, command_timeout_s=.1, landing_timeout_s=1.)
    sdk.publish_state(h=150, tof=150)
    b.observe(); sdk.acks = False
    b.begin(Action(kind='forward', value=50), 'move')
    clock.advance(.2); b.tick()
    assert b.poll().status == 'unknown'
    b.stop_motion(); b.begin(Action(kind='land'), 'land')
    sdk.responses.append(b'ok')  # The old movement's delayed reply.
    b.tick()
    assert b.poll() is None and not b.observe().landed
    clock.advance(.2); sdk.publish_state(h=0, tof=5); b.tick()
    clock.advance(.55); sdk.publish_state(h=0, tof=5); b.tick()
    result = b.poll()
    assert result is not None and result.status == 'completed'
    assert b.observe().landed
    assert sdk.wire.count('forward 50') == sdk.wire.count('land') == 1


def test_land_ack_with_high_telemetry_is_not_completed(tmp_path):
    clock, sdk, b, _ = setup(tmp_path, landing_timeout_s=.2)
    sdk.publish_state(h=150, tof=150); b.observe()
    b.begin(Action(kind='land'), 'land'); b.tick()
    assert b.poll() is None and not b.observe().landed
    clock.advance(.3); b.tick()
    assert b.poll().status == 'unknown'


def test_stale_telemetry_cannot_confirm_landing_or_allow_climb(tmp_path):
    clock, sdk, b, _ = setup(tmp_path)
    b.observe(); clock.advance(2.); sdk.publish_frame()
    observation = b.observe()
    assert not observation.connected and not observation.landed
    with pytest.raises(Exception, match='telemetry_unavailable'):
        b.begin(Action(kind='up', value=100), 'up')


def test_climb_uses_measured_height_and_land_bypasses_boundary(tmp_path):
    _, sdk, b, _ = setup(tmp_path)
    sdk.publish_state(h=450, tof=450); b.observe()
    with pytest.raises(Exception, match='boundary_violation'):
        b.begin(Action(kind='up', value=100), 'up')
    sdk.publish_state(h=600, tof=600); b.observe()
    b.begin(Action(kind='land'), 'land')
    assert sdk.wire[-1] == 'land'


def test_close_never_calls_sdk_end_or_issues_unrecorded_land(tmp_path):
    _, sdk, b, _ = setup(tmp_path)
    b.close(); b.close()
    assert not any(call[0] == 'end' for call in sdk.calls)
    assert 'land' not in sdk.wire


def test_capture_accepts_new_exposure_and_preserves_color_and_wall_time(tmp_path):
    import threading
    _, sdk, b, _ = setup(tmp_path)
    previous = b.observe()
    timer = threading.Timer(.02, sdk.publish_frame)
    timer.start()
    try: captured = b.capture()
    finally: timer.join()
    assert captured.frame_id != previous.frame_id
    assert abs(captured.captured_at - time.time()) < 1
    decoded = cv2.imdecode(np.frombuffer(captured.image_png, np.uint8), cv2.IMREAD_COLOR)
    assert decoded[0, 0].tolist() == [10, 50, 220]


def test_cached_ground_sample_cannot_confirm_landing(tmp_path):
    clock, sdk, b, _ = setup(tmp_path)
    b.begin(Action(kind='land'), 'land')
    clock.advance(.1); sdk.publish_state(h=0, tof=5); b.tick()
    clock.advance(.6); b.tick()
    assert not b.observe().landed and b.poll() is None


def test_invalid_height_blocks_climb_and_low_tof_cannot_hide_high_h(tmp_path):
    _, sdk, b, _ = setup(tmp_path)
    sdk.publish_state(h=480, tof=80); b.observe()
    with pytest.raises(Exception, match='boundary_violation'):
        b.begin(Action(kind='up', value=50), 'up')
    sdk.publish_state(h=float('nan'), tof=6553); b.observe()
    with pytest.raises(Exception, match='telemetry_unavailable'):
        b.begin(Action(kind='up', value=20), 'up')


def test_runtime_checks_measured_boundary_during_inference(tmp_path):
    _, sdk, b, r = setup(tmp_path)
    sdk.publish_state(h=550, tof=550)
    with pytest.raises(MissionEnd, match='boundary_violation'): r.service()


def test_landing_with_lost_ack_closes_command_channel(tmp_path):
    clock, sdk, b, _ = setup(tmp_path)
    sdk.acks = False
    b.begin(Action(kind='land'), 'land')
    clock.advance(.1); sdk.publish_state(); b.tick()
    clock.advance(.6); sdk.publish_state(); b.tick()
    assert b.poll().status == 'completed'
    sdk.responses.append(b'ok')
    with pytest.raises(Exception, match='command_channel_unknown'):
        b.begin(Action(kind='takeoff'), 'again')


def test_closed_backend_cannot_be_reopened_by_cached_telemetry(tmp_path):
    _, sdk, b, _ = setup(tmp_path)
    b.close(); sdk.publish_state()
    assert not b.observe().connected
    with pytest.raises(Exception, match='link_closed'):
        b.begin(Action(kind='takeoff'), 'takeoff')


class StreamingSdk(WireSdk):
    """Independent 30 Hz producer, with physical effects separate from ACKs."""
    def __init__(self, fault=None):
        import threading
        self.fault = fault
        self.freeze_video = self.freeze_state = False
        super().__init__(time.monotonic)
        self.stopped = threading.Event()
        self.worker = threading.Thread(target=self._produce, daemon=True)
        self.worker.start()

    def _produce(self):
        while not self.stopped.wait(.03):
            if not self.freeze_state: self.publish_state()
            if not self.freeze_video: self.publish_frame()

    def send_command_without_return(self, command):
        if command == 'takeoff':
            self.height_cm = self.tof_cm = 150
            if self.fault == 'lost_takeoff': self.acks = False
            if self.fault == 'video_freeze': self.freeze_video = True
            if self.fault == 'state_freeze': self.freeze_state = True
            if self.fault == 'low_battery': self.battery = 15
        elif command == 'land':
            self.height_cm, self.tof_cm = 0, 5
        super().send_command_without_return(command)

    def close_link(self):
        self.stopped.set()
        self.worker.join(timeout=1.)


def test_complete_photography_loop_on_tello_backend(tmp_path):
    from drone_agent.agent import AgentLoop
    from native_helpers import review_arguments
    from test_loop_runtime import Policy
    config = Config(max_references=0, landing_timeout_s=2.)
    sdk = StreamingSdk()
    backend = TelloBackend(sdk, config)
    artifacts = Artifacts(tmp_path, config)
    try:
        backend.connect()
        policy = Policy([('act', {'kind':'takeoff'}), ('capture', {}),
            ('review_photo', review_arguments('crop_000001') | {'next_step':'continue'}),
            ('act', {'kind':'forward', 'value':50}), ('capture', {}),
            ('review_photo', review_arguments('crop_000002')),
            ('act', {'kind':'land'}), ('finish', {'shot_id':'crop_000002'})])
        summary = AgentLoop(Runtime(backend,config,artifacts),policy,artifacts,config).run()
    finally:
        backend.close(); sdk.close_link()
    assert summary['status'] == 'completed'
    assert summary['selected_id'] == 'crop_000002'
    assert summary['landed'] and summary['landing']['source'] == 'model'
    assert len(artifacts.shots) == 2 and len(artifacts.navigation) > 2
    assert sdk.wire.count('takeoff') == sdk.wire.count('forward 50') == sdk.wire.count('land') == 1


@pytest.mark.parametrize('fault,reason,landed', [
    ('lost_takeoff', 'unknown_action', True),
    ('video_freeze', 'stale_image', True),
    ('low_battery', 'low_battery', True),
    ('state_freeze', 'link_down', False),
])
def test_agent_recovers_faults_without_repeating_motion(tmp_path,fault,reason,landed):
    from drone_agent.agent import AgentLoop
    from test_loop_runtime import Policy
    from native_helpers import reply
    config = Config(max_references=0,takeoff_timeout_s=.1,landing_timeout_s=1.,max_image_age_s=.15)
    sdk = StreamingSdk(fault)
    backend = TelloBackend(sdk,config)
    artifacts = Artifacts(tmp_path,config)
    def slow_model(_):
        time.sleep(1.3)
        return reply('act',{'kind':'forward','value':50})
    try:
        backend.connect()
        summary=AgentLoop(Runtime(backend,config,artifacts),
            Policy([('act',{'kind':'takeoff'}),slow_model]),artifacts,config).run()
    finally:
        backend.close();sdk.close_link()
    assert summary['status']=='aborted' and summary['reason']==reason
    assert summary['landed'] is landed
    assert sdk.wire.count('land')==1 and sdk.wire.count('takeoff')==1
    assert 'forward 50' not in sdk.wire
    assert summary['landing']['source']=='recovery'
    assert summary['landing']['confirmed'] is landed


def test_ack_whitespace_is_normalized_but_unrelated_text_is_not_success(tmp_path):
    _, sdk, b, _ = setup(tmp_path)
    sdk.acks=False
    b.begin(Action(kind='forward',value=20),'move')
    sdk.responses.append(b'OK\r\n')
    b.tick()
    assert b.poll().status=='completed'
    b.begin(Action(kind='back',value=20),'back')
    sdk.responses.append(b'not ok')
    b.tick()
    assert b.poll().status=='unknown'


def test_initialization_failure_leaves_summary_and_closes_link(tmp_path):
    from drone_agent.tello_node import run
    sdk=WireSdk(time.monotonic)
    sdk.fail_methods={'connect'}
    result=run(Config(max_references=0),tmp_path,preview=False,aircraft=sdk)
    assert result['status']=='aborted' and not result['landed']
    assert ('close_link',) in sdk.calls
    assert not sdk.wire


@pytest.mark.parametrize('fault', ['cancel', 'bad_video', 'boundary'])
def test_recovery_survives_fault_with_live_preview(tmp_path,fault):
    from drone_agent.agent import AgentLoop
    from drone_agent.preview import PreviewWriter
    from test_loop_runtime import Policy
    from native_helpers import reply
    config=Config(max_references=0,landing_timeout_s=1.)
    sdk=StreamingSdk()
    backend=TelloBackend(sdk,config)
    artifacts=Artifacts(tmp_path,config)
    preview=PreviewWriter(tmp_path)
    def fault_during_model(_):
        if fault=='cancel': (tmp_path/'stop.request').touch()
        elif fault=='bad_video':
            sdk._reader.frame=np.zeros((200,300,3),np.uint8)
            sdk.publish_frame()
        else:
            sdk.height_cm=sdk.tof_cm=600
            sdk.publish_state()
        time.sleep(.15)
        return reply('act',{'kind':'forward','value':50})
    try:
        backend.connect()
        summary=AgentLoop(Runtime(backend,config,artifacts,preview=preview),
            Policy([('act',{'kind':'takeoff'}),fault_during_model]),artifacts,config).run()
    finally:
        preview.close();backend.close();sdk.close_link()
    assert summary['status']=='aborted'
    assert sdk.wire.count('land')==1 and 'forward 50' not in sdk.wire
    assert summary['landed'] and summary['landing']['source']=='recovery'


def test_stop_confirmation_needs_post_stop_stationary_telemetry(tmp_path):
    clock,sdk,b,_=setup(tmp_path)
    sdk.publish_state(h=150,tof=150,vgx=40)
    b.begin(Action(kind='stop'),'stop');b.tick()
    assert b.poll() is None
    clock.advance(.1);sdk.publish_state(h=150,tof=150,vgx=0);b.tick()
    assert b.poll().status=='completed'


def test_runtime_duplicate_id_dispatches_wire_only_once(tmp_path):
    _,sdk,_,runtime=setup(tmp_path)
    action=Action(kind='speed',value=30)
    first=runtime.execute(action,'same','frame_000001')
    second=runtime.execute(action,'same','frame_000001')
    assert first==second and sdk.wire.count('speed 30')==1


def test_timed_out_channel_rejects_further_motion_even_after_late_reply(tmp_path):
    clock,sdk,b,_=setup(tmp_path,command_timeout_s=.1)
    sdk.acks=False
    b.begin(Action(kind='forward',value=20),'move')
    clock.advance(.2);b.tick()
    assert b.poll().status=='unknown'
    sdk.responses.append(b'ok');b.tick()
    with pytest.raises(Exception,match='command_channel_unknown'):
        b.begin(Action(kind='back',value=20),'back')
    assert sdk.wire==['forward 20']
