"""The contract both backends must satisfy, plus TelloBackend's own edge cases.

The first half is deliberately written against the *seam*, not against either
implementation: `test_both_backends_agree` runs the same assertions over
`FakeBackend` and `TelloBackend` so the two cannot drift apart silently. The
second half exercises behaviour only the hardware path has — SDK timeouts, the
host `hold`, the command-based radius bound — through `FakeTelloSdk` rather than a real
aircraft.
"""
from __future__ import annotations

import math
import time

import numpy as np
import pytest
from backends import FakeBackend, FakeTelloSdk

from drone_agent.backend import BackendError
from drone_agent.flight import body_to_world
from drone_agent.protocol import Action, Config
from drone_agent.tello_backend import TelloBackend, sdk_yaw_to_navigation

FRAME = np.full((720, 960, 3), [30, 60, 200], np.uint8)


def config(**over):
    return Config(**{'command_timeout_s': 5., 'takeoff_timeout_s': 5.,
                     'landing_timeout_s': 5., **over})


def tello(**over):
    """A TelloBackend over a fake SDK, plus the fake for assertions."""
    sdk = FakeTelloSdk(frame=FRAME.copy(), **over.pop('sdk', {}))
    backend = TelloBackend(sdk, config(**over))
    backend.connect()
    return backend, sdk


def deliver(backend, action, identity):
    """Run one command to completion, driving `tick` as the runtime would."""
    backend.begin(action, identity)
    for _ in range(200):
        backend.tick()
        result = backend.poll()
        if result is not None:
            return result
        time.sleep(.005)
    raise AssertionError('command never completed')


# -- the shared seam ------------------------------------------------------

def both():
    """One of each backend, so a contract test can assert against the pair."""
    return [('fake', FakeBackend()), ('tello', tello()[0])]


@pytest.mark.parametrize('name,backend', both())
def test_seam_answers_every_documented_method(name, backend):
    """`Backend` is a Protocol, so nothing checks this at runtime but this test."""
    for method in ('tick', 'observe', 'capture', 'begin', 'poll', 'keepalive',
                   'stop_motion', 'close'):
        assert callable(getattr(backend, method)), f'{name} is missing {method}'


def test_poll_is_none_until_the_command_settles():
    """`None` means "still running"; answering early would end a mission.

    Tello only. The fake settles synchronously inside `begin`, so it has no
    pending phase to observe; the hardware path must have a polled reply.
    """
    backend, _ = tello()
    backend.observe()
    backend.begin(Action(kind='takeoff'), 'id_1')
    assert backend.poll() is None, 'takeoff claimed completion before any tick'
    for _ in range(200):
        backend.tick()
        result = backend.poll()
        if result is not None:
            break
        time.sleep(.005)
    assert result is not None and result.status == 'completed'


@pytest.mark.parametrize('name,backend', both())
def test_a_command_reaches_exactly_one_terminal_state(name, backend):
    """Every backend answers one `begin` with one result, then goes quiet."""
    backend.observe()
    backend.begin(Action(kind='takeoff'), 'id_1')
    seen = None
    for _ in range(200):
        backend.tick()
        result = backend.poll()
        if result is not None:
            seen = result
            break
        time.sleep(.005)
    assert seen is not None and seen.action_id == 'id_1'
    assert seen.status in ('completed', 'unknown', 'rejected')
    assert backend.poll() is None, 'a settled command answered twice'


# -- TelloBackend: the wire --------------------------------------------------

def test_connect_is_idempotent():
    """The SDK's `command` handshake races an active stream; connect twice safely."""
    backend, sdk = tello()
    backend.connect()
    backend.connect()
    assert [c for c in sdk.calls if c[0] == 'connect'] == [('connect',)]


def test_flight_command_reaches_the_sdk_exactly_once():
    backend, sdk = tello()
    result = deliver(backend, Action(kind='forward', value=50), 'id_1')
    assert result.status == 'completed'
    assert [c for c in sdk.calls if c[0] == 'move_forward'] == [('move_forward', 50)]


def test_a_slow_command_times_out_as_unknown_never_rejected():
    """`unknown` is what latches `motion_unknown`, forbidding a retry.

    Reporting `rejected` here would tell the model the aircraft had not moved
    when in fact the command reached it and may have.
    """
    backend, sdk = tello(command_timeout_s=0.05, sdk={'latency_s': 0.4})
    backend.begin(Action(kind='forward', value=30), 'id_1')
    deadline = time.monotonic() + 2.
    while time.monotonic() < deadline:
        backend.tick()
        result = backend.poll()
        if result is not None:
            break
        time.sleep(.01)
    assert result.status == 'unknown'
    assert result.reason == 'command_completion_timeout'


def test_a_hold_is_a_host_wait_and_touches_no_sdk_method():
    """`hold` waits on wall clock; crediting the aircraft with it would be a lie."""
    backend, sdk = tello()
    before = len(sdk.calls)
    assert deliver(backend, Action(kind='hold', value=1), 'id_1').status == 'completed'
    assert len(sdk.calls) == before


def test_a_wire_send_error_becomes_unknown_not_a_crash():
    backend, sdk = tello(sdk={'fail_methods': {'move_left'}})
    result = deliver(backend, Action(kind='left', value=20), 'id_1')
    assert result.status == 'unknown'
    assert result.reason == 'sdk_error'


def test_stop_sends_the_sdk_stop_command():
    backend, sdk = tello()
    result = deliver(backend, Action(kind='stop'), 'id_1')
    assert result.status == 'completed'
    assert sdk.wire == ['stop']


def test_keepalive_refuses_to_interleave_into_a_moving_command():
    """The SDK's command window is short; a zero-RC curtails an active leg."""
    backend, sdk = tello()
    backend.begin(Action(kind='forward', value=50), 'id_1')
    assert backend.keepalive() is False


def test_keepalive_sends_zero_rc_when_idle():
    backend, sdk = tello()
    backend.connect()
    assert backend.keepalive() is True
    assert ('send_rc_control', 0, 0, 0, 0) in sdk.calls


# -- TelloBackend: telemetry -------------------------------------------------

def test_altitude_prefers_the_tof():
    backend, _ = tello(sdk={'tof_cm': 220, 'height_cm': 999})
    assert backend.altitude_cm() == 220.


def test_altitude_falls_back_to_the_barometer_when_the_tof_saturates():
    """Over grass the ToF reads the out-of-range constant, not an error."""
    backend, _ = tello(sdk={'tof_cm': 6553, 'height_cm': 180})
    assert backend.altitude_cm() == 180.


def test_altitude_falls_back_when_the_tof_getter_is_absent():
    backend, sdk = tello()
    del sdk.tof_cm
    sdk.get_distance_tof = lambda: (_ for _ in ()).throw(AttributeError('no tof'))
    assert backend.altitude_cm() == 150.


def test_altitude_beyond_the_trusted_tof_range_uses_the_barometer():
    backend, _ = tello(sdk={'tof_cm': 900, 'height_cm': 905})
    assert backend.altitude_cm() == 905.


def test_no_telemetry_leaks_into_the_observation():
    """The model sees pixels and a battery number, never a position."""
    backend, _ = tello(sdk={'tof_cm': 137, 'yaw_deg': 42})
    fields = set(backend.observe().model_dump())
    assert fields == {'frame_id', 'captured_at', 'received_at', 'image_png',
                      'battery_pct', 'connected', 'airborne', 'landed'}


def test_missing_battery_field_does_not_fake_a_low_battery():
    backend, sdk = tello()
    sdk.battery = None
    backend.battery_pct = 88.
    assert backend.observe().battery_pct == 88.


def test_camera_size_mismatch_is_refused_not_silently_downscaled():
    backend, _ = tello()
    backend.sdk._reader.frame = np.zeros((480, 640, 3), np.uint8)
    with pytest.raises(BackendError) as caught:
        backend.capture()
    assert caught.value.code == 'camera_profile_mismatch'


# -- TelloBackend: the fence -------------------------------------------------

def test_the_fence_refuses_a_projected_breach_before_dispatch():
    """Refuse rather than dispatch and then abort: nothing is sent to the wire."""
    backend, sdk = tello(radius_m=3.)
    with pytest.raises(BackendError) as caught:
        backend.begin(Action(kind='forward', value=400), 'id_1')  # a 4 m leg
    assert caught.value.code == 'boundary_violation'
    assert not [c for c in sdk.calls if c[0] == 'move_forward']


def test_the_fence_closes_after_enough_acknowledged_legs():
    backend, sdk = tello(radius_m=1.)
    assert deliver(backend, Action(kind='forward', value=100), 'id_1').status == 'completed'
    assert backend.outside_boundary() is None
    with pytest.raises(BackendError) as caught:
        backend.begin(Action(kind='forward', value=100), 'id_2')
    assert caught.value.code == 'boundary_violation'


def test_translation_accumulates_in_the_heading_frame():
    """The estimate must use the same convention the flights controller does."""
    backend, sdk = tello(radius_m=100., sdk={'yaw_deg': 0})
    deliver(backend, Action(kind='forward', value=100), 'id_1')
    dx, dy = body_to_world(1., 0., backend._yaw)  # the call the estimate makes
    assert (backend._x_cm, backend._y_cm) == pytest.approx((dx * 100., dy * 100.))


def test_rotation_does_not_breach_the_fence():
    """A yaw command cannot change position, so it is never a fence violation."""
    backend, _ = tello(radius_m=1.)
    assert deliver(backend, Action(kind='cw', value=90), 'id_1').status == 'completed'


def test_ceiling_is_enforced_on_climb():
    backend, _ = tello(ceiling_m=2.)
    deliver(backend, Action(kind='takeoff'), 'id_1')
    with pytest.raises(BackendError) as caught:
        backend.begin(Action(kind='up', value=300), 'id_2')
    assert caught.value.code == 'boundary_violation'


# -- the two backends must agree ---------------------------------------------

def test_sdk_yaw_is_already_the_navigation_heading():
    """Guards the 90 degree trap: applying the heading transform twice shows here.

    Compared as a circular distance, because pi and -pi name the same heading.
    """
    for degrees in (0, 45, 90, 180, 270, -90):
        got = sdk_yaw_to_navigation(degrees)
        expected = math.radians(degrees)
        gap = math.atan2(math.sin(got - expected), math.cos(got - expected))
        assert abs(gap) < 1e-9, f'{degrees} deg came back {math.degrees(gap):.3f} off'
