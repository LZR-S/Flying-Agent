"""Single-send Tello commands, timestamped sensors and conservative recovery.

UDP replies have no command IDs. Once a reply is lost or an action interrupted,
this session never trusts another ACK. Only stop/land remain available; landing
requires fresh, stable ground telemetry. Horizontal bounds remain command-based
estimates, not measured positions.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import cv2

from .backend import BackendError
from .flight import body_to_world, normalise_angle
from .protocol import Action, ActionResult, Observation

TOF_MAX_TRUSTED_CM = 600
TOF_OUT_OF_RANGE_CM = 6553
TELEMETRY_MAX_AGE_S = 1.0
LAND_STABLE_S = .5


def sdk_yaw_to_navigation(yaw_deg: float) -> float:
    """Convert the SDK yaw unit; hardware heading convention needs flight validation."""
    return normalise_angle(math.radians(yaw_deg))


@dataclass
class _InFlight:
    action: Action
    identity: str
    started: float
    deadline: float
    heading: float
    acknowledged: bool = False


class TelloBackend:
    keepalive_command = 'rc 0 0 0 0'

    def __init__(self, sdk, config, *, clock=time.monotonic):
        self.sdk = sdk
        self.config = config
        self.clock = clock
        self.connected = False
        self.airborne = False
        self.landed = False
        self.streaming = False
        self.battery_pct = 100.
        self.speed_cm_s = config.speed_cm_s
        self.frame = None
        self.active = None
        self.result = None
        self._opened = False
        self._closed = False
        self._recovering = False
        self._tainted = False
        self._possibly_airborne = False
        self._landing_allowed = True
        self._ground_since = None
        self._state_seq = None
        self._state_at = -math.inf
        self._state = {}
        self._frame_seq = None
        self._x_cm = self._y_cm = self._yaw = 0.
        self._altitude_cm = None

    def connect(self):
        if self._opened:
            return
        try:
            self.sdk.retry_count = 1
            self.sdk.connect()
            self.sdk.set_speed(self.config.speed_cm_s)
            self.sdk.streamon()
            self.streaming = True
            self.sdk.get_frame_read()
        except Exception as error:
            raise BackendError('sdk_initialization_error') from error
        self._opened = True
        # Decoder startup is bounded and happens before any flight command.
        deadline = time.monotonic() + 5.
        while True:
            self.tick()
            if self.frame is not None and self.connected:
                return
            if time.monotonic() >= deadline:
                raise BackendError('sensor_initialization_timeout')
            time.sleep(.01)

    def _read_state(self):
        sample = self.sdk.state_sample()
        now = self.clock()
        if sample is not None:
            seq, received, state = sample
            if seq != self._state_seq:
                previous_at = self._state_at
                self._state_seq, self._state_at = seq, received
                self._state = state
                if received - previous_at > TELEMETRY_MAX_AGE_S:
                    self._ground_since = None
                if now - received <= TELEMETRY_MAX_AGE_S:
                    battery = state.get('bat')
                    if isinstance(battery, (int, float)) and 0 <= battery <= 100:
                        self.battery_pct = float(battery)
                    self._altitude_cm = self._height(state)
                    yaw = state.get('yaw')
                    if self._finite(yaw):
                        self._yaw = sdk_yaw_to_navigation(yaw)
                    ground = self._ground_evidence(state)
                    if ground and self._landing_allowed:
                        if self._ground_since is None:
                            self._ground_since = received
                        self.landed = received - self._ground_since >= LAND_STABLE_S
                    else:
                        self._ground_since = None
                        self.landed = False
                    if self.landed:
                        self._possibly_airborne = False
                    elif self._altitude_cm is not None and self._altitude_cm > 20:
                        self._possibly_airborne = True
        self.connected = self._opened and not self._closed and now - self._state_at <= TELEMETRY_MAX_AGE_S
        if not self.connected:
            self.landed = False
            self._ground_since = None
            self._altitude_cm = None
        self.airborne = self._possibly_airborne and not self.landed

    @staticmethod
    def _finite(value):
        return isinstance(value, (int, float)) and math.isfinite(value)

    @classmethod
    def _height(cls, state):
        tof, height = state.get('tof'), state.get('h')
        # h is relative to the takeoff surface; ToF can see furniture underneath.
        usable = [v for v in (height,) if cls._finite(v) and v >= 0]
        if cls._finite(tof) and 0 < tof < TOF_MAX_TRUSTED_CM:
            usable.append(tof)
        return float(max(usable)) if usable else None

    @classmethod
    def _ground_evidence(cls, state):
        fields = ('h', 'tof', 'vgx', 'vgy', 'vgz', 'roll', 'pitch')
        if not all(cls._finite(state.get(k)) for k in fields):
            return False
        return (0 <= state['h'] <= 10 and 0 < state['tof'] <= 20
                and all(abs(state[k]) <= 5 for k in ('vgx', 'vgy', 'vgz'))
                and all(abs(state[k]) <= 10 for k in ('roll', 'pitch')))

    def altitude_cm(self):
        """Raw ToF with h fallback, for diagnostics; bounds use both conservatively."""
        self._read_state()
        if not self.connected:
            raise BackendError('telemetry_unavailable')
        tof = self._state.get('tof')
        if self._finite(tof) and 0 < tof < TOF_MAX_TRUSTED_CM:
            return float(tof)
        height = self._state.get('h')
        if not self._finite(height) or height < 0:
            raise BackendError('telemetry_unavailable')
        return float(height)

    def _read_frame(self):
        sample = self.sdk.frame_sample()
        if sample is None:
            return
        seq, received, captured, rgb = sample
        if seq == self._frame_seq:
            return
        if rgb.ndim != 3 or rgb.shape != (self.config.video_height, self.config.video_width, 3):
            raise BackendError('camera_profile_mismatch')
        ok, encoded = cv2.imencode('.png', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if not ok:
            raise BackendError('image_encode_failed')
        self._frame_seq = seq
        self.frame = Observation(frame_id=f'frame_{seq:06}', captured_at=captured,
            received_at=received, image_png=encoded.tobytes(), battery_pct=self.battery_pct,
            connected=self.connected, airborne=self.airborne, landed=self.landed)

    def tick(self):
        if self._closed:
            return
        self._read_state()
        self._settle()
        try:
            self._read_frame()
        except BackendError:
            if not self._recovering or self.frame is None:
                raise

    def observe(self):
        self.tick()
        if self.frame is None:
            raise BackendError('frame_unavailable')
        return self.frame.model_copy(update={'battery_pct':self.battery_pct,
            'connected':self.connected, 'airborne':self.airborne, 'landed':self.landed})

    def capture(self):
        self.tick()
        before = self._frame_seq
        started = self.clock()
        deadline = time.monotonic() + self.config.max_image_age_s
        while time.monotonic() < deadline:
            self.tick()
            if self._frame_seq != before and self.frame.received_at >= started:
                return self.observe()
            time.sleep(.005)
        raise BackendError('fresh_frame_timeout')

    def _responses(self):
        responses = self.sdk.get_own_udp_object()['responses']
        items = []
        while responses:
            items.append(responses.pop(0).strip().lower())
        return items

    def _send(self, wire):
        try:
            self.sdk.send_command_without_return(wire)
        except Exception as error:
            raise BackendError('sdk_error') from error

    def begin(self, action: Action, identity: str):
        if self.active is not None:
            raise BackendError('concurrent_command')
        self._read_state()
        if self._closed or not self._opened:
            raise BackendError('link_closed')
        if self._tainted and action.kind not in ('land', 'stop'):
            raise BackendError('command_channel_unknown')
        if action.kind not in ('land', 'stop', 'hold'):
            if not self.connected or self._altitude_cm is None or not self._finite(self._state.get('yaw')):
                raise BackendError('telemetry_unavailable')
            if self.outside_boundary() or self._projected_breach(action):
                raise BackendError('boundary_violation')
        self.result = None
        self._responses()
        now = self.clock()
        timeout = (self.config.takeoff_timeout_s if action.kind == 'takeoff' else
                   self.config.landing_timeout_s if action.kind == 'land' else
                   action.value if action.kind == 'hold' else self.config.command_timeout_s)
        self.active = _InFlight(action, identity, now, now + timeout, self._yaw)
        if action.kind == 'takeoff':
            # Until a subsequent land, missing takeoff evidence never means grounded.
            self._possibly_airborne = self.airborne = True
            self.landed = False
            self._landing_allowed = False
            self._ground_since = None
        elif action.kind == 'land':
            self._landing_allowed = True
            self.landed = False
            self._ground_since = None
        if action.kind == 'hold':
            return
        try:
            self._send(action.sdk_command())
        except BackendError:
            self._terminal('unknown', 'sdk_error')

    def _terminal(self, status, reason=''):
        command = self.active
        self.result = ActionResult(action_id=command.identity, status=status, reason=reason)
        if status == 'unknown':
            self._tainted = True
        if status == 'completed':
            kind, value = command.action.kind, command.action.value
            if kind == 'speed':
                self.speed_cm_s = value
            elif kind in ('forward', 'back', 'left', 'right'):
                forward = value if kind == 'forward' else -value if kind == 'back' else 0
                left = value if kind == 'left' else -value if kind == 'right' else 0
                dx, dy = body_to_world(forward / 100., left / 100., command.heading)
                self._x_cm += dx * 100.
                self._y_cm += dy * 100.
        self.active = None

    def _settle(self):
        replies = self._responses()
        if self.active is None:
            return
        command = self.active
        kind = command.action.kind
        now = self.clock()
        if kind == 'hold':
            if now >= command.deadline:
                self._terminal('completed')
            return
        # A timeout takes precedence over any reply observed after its deadline.
        if now >= command.deadline:
            self._terminal('unknown', 'command_completion_timeout')
            return
        if kind == 'stop' and not self._tainted:
            if replies == [b'ok']:
                command.acknowledged = True
            elif replies:
                self._terminal('unknown', 'sdk_error')
                return
            stationary = all(self._finite(self._state.get(k)) and abs(self._state[k]) <= 5
                             for k in ('vgx', 'vgy', 'vgz'))
            if command.acknowledged and self.connected and self._state_at > command.started and stationary:
                self._terminal('completed')
            return
        if kind == 'land':
            if not self._tainted and replies == [b'ok']:
                command.acknowledged = True
            if self.landed and self._state_at > command.started:
                if not command.acknowledged:
                    self._tainted = True
                self._terminal('completed')
            return
        if self._tainted:
            if kind == 'stop':
                self._terminal('unknown', 'command_channel_unknown')
            return
        if replies:
            if replies == [b'ok']:
                self._terminal('completed')
            else:
                self._terminal('unknown', 'sdk_error')

    def poll(self):
        result, self.result = self.result, None
        return result

    def outside_boundary(self):
        if math.hypot(self._x_cm, self._y_cm) / 100. > self.config.radius_m:
            return 'radius'
        if self._altitude_cm is not None and self._altitude_cm / 100. > self.config.ceiling_m:
            return 'ceiling'
        return None

    def _projected_breach(self, action):
        kind, value = action.kind, action.value
        if kind in ('forward', 'back', 'left', 'right'):
            forward = value if kind == 'forward' else -value if kind == 'back' else 0
            left = value if kind == 'left' else -value if kind == 'right' else 0
            dx, dy = body_to_world(forward / 100., left / 100., self._yaw)
            if math.hypot(self._x_cm + dx * 100., self._y_cm + dy * 100.) / 100. > self.config.radius_m:
                return 'radius'
        elif kind == 'up' and (self._altitude_cm + value) / 100. > self.config.ceiling_m:
            return 'ceiling'
        return None

    def keepalive(self):
        if not self.connected or self._closed or (self.active and self.active.action.kind != 'hold'):
            return False
        try:
            self._send(self.keepalive_command)
        except BackendError:
            return False
        return True

    def stop_motion(self):
        self._recovering = True
        if self.active and self.active.action.kind != 'hold':
            self._tainted = True
        self.active = self.result = None
        if not self._opened or self._closed:
            return
        # stop itself produces an uncorrelated reply, so recovery never consumes ACKs.
        self._tainted = True
        try:
            self._send('stop')
        except BackendError:
            pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.active = self.result = None
        self.connected = False
        self.sdk.close_link()
