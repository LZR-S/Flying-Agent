"""Shared stand-ins for the backend seam.

Three test modules used to hand-build their own fake aircraft, each in a
different shape. They now share `FakeBackend` and `FakeFlight`, so a change to
the `Backend` contract has one place to land instead of three.
"""
from __future__ import annotations

import time
from typing import Callable

from drone_agent.protocol import Action, ActionResult, Observation
from test_protocol_context import obs

__all__ = ['FakeBackend', 'FakeFlight', 'build_backend']


class FakeFlight:
    """The subset of `RotorFlightController` that `CommandState` touches.

    Holds mutable *instance* state, unlike the class-level stub it replaces:
    two `FakeFlight` objects must not share a target.
    """

    def __init__(self, *, position=(10., 20., 1.6), yaw=0.):
        self.elapsed_s = 0.
        self.position = tuple(position)
        self.altitude_m = position[2]
        self.yaw = yaw
        self.flying = True
        self.target_xy = self.position[:2]
        self.target_altitude = self.altitude_m
        self.target_yaw = self.yaw
        self._alt_integral = 0.
        self.velocity = (0., 0., 0.)
        self.reached = False
        self.stopped = False

    def set_target(self, *, xy=None, altitude=None, yaw=None):
        if xy is not None:
            self.target_xy = tuple(xy)
        if altitude is not None:
            self.target_altitude = float(altitude)
        if yaw is not None:
            self.target_yaw = float(yaw)

    def hold_current(self):
        self.set_target(xy=self.position[:2], altitude=self.altitude_m, yaw=self.yaw)

    def clear_integrals(self):
        self._alt_integral = 0.

    def linear_reached(self, tolerance):
        return self.reached

    def yaw_reached(self, tolerance):
        return self.reached

    def stop(self):
        self.flying = False
        self.stopped = True


class FakeBackend:
    """A deterministic aircraft that satisfies `Backend` without Webots.

    Default policy: every command completes on the next tick. Tests override
    `poll`/`tick`/`observe` to model timeouts, faults and lost links.
    """

    def __init__(self, *, landed=True, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.seq = 1
        self.airborne = not landed
        self.active = None
        self.sent = []
        self.fail = False
        self.closed = False
        self.keepalives = 0
        self.connected = True
        self.battery_pct = 100.

    def tick(self):
        self.seq += 1
        if self.active:
            if self.active[1].kind == 'takeoff':
                self.airborne = True
            if self.active[1].kind == 'land':
                self.airborne = False
        time.sleep(.001)

    def observe(self):
        return obs(self.seq).model_copy(update={'received_at': self.clock(), 'airborne': self.airborne,
                                                'landed': not self.airborne})

    def capture(self):
        self.tick()
        return self.observe()

    def begin(self, action, identity):
        self.sent.append(action.kind)
        self.active = (identity, action)

    def poll(self):
        if not self.active:
            return None
        identity, action = self.active
        self.active = None
        return ActionResult(action_id=identity, status='unknown' if self.fail else 'completed')

    def keepalive(self):
        self.keepalives += 1
        return True

    def stop_motion(self):
        self.active = None

    def close(self):
        self.closed = True


def build_backend(*, landed=True, clock: Callable[[], float] = time.monotonic):
    """Constructor used by tests that only need the default fake."""
    return FakeBackend(landed=landed, clock=clock)


class FakeFrameReader:
    def __init__(self, frame=None):
        self.frame = frame


class FakeTelloSdk:
    """Timestamped SDK stand-in for contract checks.

    State packets update on polling; new pixel objects represent decoder frames.
    Wire latency delays replies without delaying the send. Fault tests use a
    separate explicit packet producer instead of this normal-operation fake.
    """

    def __init__(self, *, battery=100, frame=None, height_cm=150, tof_cm=150,
                 yaw_deg=0, latency_s=0., fail_methods=()):
        self.battery = battery
        self.calls = []
        self._reader = FakeFrameReader(frame)
        self.height_cm = height_cm
        self.tof_cm = tof_cm
        self.yaw_deg = yaw_deg
        self.latency_s = latency_s
        self.fail_methods = set(fail_methods)
        self.connected = False
        self.streaming = False
        self._responses = []
        self._pending = []
        self._sample_seq = 0
        self._video_seq = 0
        self._video_object = None
        self._video = None
        self.wire = []

    def state_sample(self):
        self._sample_seq += 1
        return self._sample_seq, time.monotonic(), {
            'h': self.height_cm, 'tof': getattr(self, 'tof_cm', 6553),
            'yaw': self.yaw_deg, 'bat': self.battery,
            'vgx': 0, 'vgy': 0, 'vgz': 0, 'roll': 0, 'pitch': 0}

    def frame_sample(self):
        if self._reader.frame is not self._video_object:
            self._video_object = self._reader.frame
            self._video_seq += 1
            self._video = (self._video_seq, time.monotonic(), time.time(), self._reader.frame)
        return self._video

    def send_command_without_return(self, command):
        self.wire.append(command)
        parts = command.split()
        kind = parts[0]
        method = {'forward':'move_forward', 'back':'move_back', 'left':'move_left',
                  'right':'move_right', 'up':'move_up', 'down':'move_down',
                  'cw':'rotate_clockwise', 'ccw':'rotate_counter_clockwise',
                  'speed':'set_speed', 'rc':'send_rc_control'}.get(kind, kind)
        self.calls.append((method, *(int(v) for v in parts[1:])))
        if method in self.fail_methods:
            raise OSError('injected send failure')
        if kind == 'takeoff': self.height_cm = self.tof_cm = 150
        if kind == 'land': self.height_cm, self.tof_cm = 0, 5
        if kind != 'rc': self._pending.append((time.monotonic() + self.latency_s, b'ok'))

    def get_own_udp_object(self):
        ready = [item for item in self._pending if item[0] <= time.monotonic()]
        self._pending = [item for item in self._pending if item[0] > time.monotonic()]
        self._responses.extend(reply for _, reply in ready)
        return {'responses': self._responses}

    def __getattr__(self, name):
        if name in {'connect', 'end', 'takeoff', 'land', 'emergency', 'move_forward',
                    'move_back', 'move_left', 'move_right', 'move_up', 'move_down',
                    'rotate_clockwise', 'rotate_counter_clockwise', 'send_rc_control',
                    'streamon', 'streamoff', 'set_speed', 'close_link'}:
            def record(*args):
                self.calls.append((name,) + args)
                if name in self.fail_methods:
                    raise OSError(f'{name} failed')
                if self.latency_s:
                    time.sleep(self.latency_s)
            return record
        raise AttributeError(name)

    def get_battery(self):
        return self.battery

    def get_frame_read(self):
        return self._reader

    def get_height(self):
        return self.height_cm

    def get_distance_tof(self):
        return self.tof_cm

    def get_yaw(self):
        return self.yaw_deg
