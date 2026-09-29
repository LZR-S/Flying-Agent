"""Webots adapter: one tick owner, private sensors, public RGB snapshots."""
import math
import random
import time
from collections import deque
import cv2
import numpy as np
from .flight import (RotorFlightController,body_to_world,normalise_angle,
                     LANDED_ALTITUDE_M,SETTLE_SPEED_MPS)
from .protocol import Observation,ActionResult

COMPOSITION_POSITION_TOLERANCE_M = .03
COMPOSITION_SETTLE_SPEED_MPS = .03
COMPOSITION_SETTLE_S = .5
TAKEOFF_HORIZONTAL_TOLERANCE_M = .15
TAKEOFF_VERTICAL_TOLERANCE_M = .10
TAKEOFF_SETTLE_SPEED_MPS = .05


class CommandState:
    """One SDK command, with a speed-limited reference for the private PID."""

    def __init__(self, flight, action, identity, *, speed_cm_s=50, takeoff_height_m=1.,
                 command_timeout_s=60., takeoff_timeout_s=20., landing_timeout_s=20.):
        self.flight = flight
        self.action = action
        self.identity = identity
        self.stable_since = None
        self.started = flight.elapsed_s
        self.tolerance = COMPOSITION_POSITION_TOLERANCE_M
        self.start_position = tuple(flight.position)
        self.destination = list(self.start_position)
        self.reference_duration = 0.
        f = flight
        kind = action.kind
        metres = action.value / 100.
        f.hold_current()
        if kind == 'takeoff':
            f.flying = True
            f.clear_integrals()
            self.destination[2] = takeoff_height_m
        elif kind == 'land':
            self.destination[2] = 0.
            self.tolerance = LANDED_ALTITUDE_M
        elif kind in ('forward', 'back', 'left', 'right'):
            dx, dy = body_to_world(metres if kind == 'forward' else -metres if kind == 'back' else 0.,
                                   metres if kind == 'left' else -metres if kind == 'right' else 0., f.yaw)
            self.destination[0] += dx
            self.destination[1] += dy
        elif kind in ('up', 'down'):
            self.destination[2] += metres if kind == 'up' else -metres
        elif kind in ('cw', 'ccw'):
            angle = math.radians(action.value) * (1 if kind == 'cw' else -1)
            self.turn_remaining = angle
            self.last_yaw = f.yaw
            f.set_target(yaw=normalise_angle(f.yaw + math.copysign(min(abs(angle), math.pi / 2), angle)))
            self.yaw_tolerance = min(math.pi / 180, max(abs(angle) / 3, math.pi / 1800))
        self.reference_duration = math.dist(self.start_position, self.destination) / (speed_cm_s / 100.)
        timeout = (takeoff_timeout_s if kind == 'takeoff' else landing_timeout_s if kind == 'land'
                   else action.value + 1 if kind == 'hold' else command_timeout_s)
        self.deadline = self.started + timeout

    def poll(self):
        f = self.flight
        kind = self.action.kind
        elapsed = f.elapsed_s - self.started
        if f.elapsed_s >= self.deadline:
            return ActionResult(action_id=self.identity, status='unknown', reason='command_completion_timeout')
        if kind in ('cw', 'ccw'):
            self.turn_remaining -= normalise_angle(f.yaw - self.last_yaw)
            self.last_yaw = f.yaw
            f.set_target(yaw=normalise_angle(f.yaw + math.copysign(min(abs(self.turn_remaining), math.pi / 2), self.turn_remaining)))
            reached = abs(self.turn_remaining) <= self.yaw_tolerance and f.yaw_reached(self.yaw_tolerance)
        elif kind in ('speed', 'stop'):
            reached = True
        elif kind == 'hold':
            reached = elapsed >= self.action.value
        else:
            fraction = min(1., elapsed / self.reference_duration) if self.reference_duration else 1.
            target = [a + fraction * (b - a) for a, b in zip(self.start_position, self.destination)]
            f.set_target(xy=target[:2], altitude=target[2])
            reached = fraction == 1. and f.linear_reached(self.tolerance)
        if kind == 'land':
            reached = reached and f.altitude_m <= LANDED_ALTITUDE_M
            if reached:
                if self.stable_since is None:
                    self.stable_since = f.elapsed_s
                reached = f.elapsed_s - self.stable_since >= .5
            else:
                self.stable_since = None
        elif kind == 'takeoff':
            reached = (fraction == 1.
                       and math.dist(f.position[:2], self.destination[:2]) <= TAKEOFF_HORIZONTAL_TOLERANCE_M
                       and abs(f.altitude_m - self.destination[2]) <= TAKEOFF_VERTICAL_TOLERANCE_M
                       and math.sqrt(sum(v*v for v in f.velocity)) <= TAKEOFF_SETTLE_SPEED_MPS)
            if reached:
                if self.stable_since is None:self.stable_since=f.elapsed_s
                reached=f.elapsed_s-self.stable_since>=COMPOSITION_SETTLE_S
            else:self.stable_since=None
        elif kind in ('forward','back','left','right','up','down'):
            reached = reached and math.sqrt(sum(v*v for v in f.velocity))<=COMPOSITION_SETTLE_SPEED_MPS
            if reached:
                if self.stable_since is None:self.stable_since=f.elapsed_s
                reached=f.elapsed_s-self.stable_since>=COMPOSITION_SETTLE_S
            else:self.stable_since=None
        if reached:
            if kind == 'land':
                f.stop()
            return ActionResult(action_id=self.identity, status='completed')
        return None


class WebotsBackend:
    def __init__(self,robot,config):
        self.robot=robot;self.config=config;self.dt=int(robot.getBasicTimeStep())
        self.camera=robot.getDevice('camera');self.camera.enable(self.dt)
        if (self.camera.getWidth(),self.camera.getHeight())!=(config.video_width,config.video_height):
            raise ValueError('camera_profile_mismatch')
        self.flight=RotorFlightController(robot,self.dt)
        if self.flight.sensor_init_failed:raise RuntimeError('sensor_initialization_failed')
        self.epoch_wall=time.monotonic();self.epoch_sim=self.flight.elapsed_s
        self.active=None;self.result=None;self.battery=100.;self.connected=True;self.speed_cm_s=config.speed_cm_s
        self.seq=0;self.last_image_sim=-math.inf;self.next_image_sim=0.;self.images=deque(maxlen=100)
        self.rng=random.Random(config.seed);self.tick()

    def tick(self):
        sim=self.flight.elapsed_s-self.epoch_sim
        delay=sim-(time.monotonic()-self.epoch_wall)
        if delay>0:time.sleep(delay)
        before=self.flight.elapsed_s;airborne=self.flight.flying
        if not self.flight.step():
            self.connected=False
            raise RuntimeError('simulator_disconnected')
        elapsed=self.flight.elapsed_s-before
        if airborne:self.battery=max(0.,self.battery-elapsed*100/self.config.simulated_battery_duration_s)
        if self.active:
            self.result=self.active.poll()
            if self.result is not None:
                if self.rng.random()<self.config.lost_reply_probability:
                    self.result=self.result.model_copy(update={'status':'unknown','reason':'lost_reply'})
                self.active=None
        sim=self.flight.elapsed_s
        if sim>=self.next_image_sim or not self.images:
            self._expose()
            interval=1/self.config.video_fps
            self.next_image_sim+=(math.floor((sim-self.next_image_sim)/interval)+1)*interval

    def _expose(self):
        pixels=self.camera.getImage()
        if pixels is None:raise RuntimeError('camera_exposure_unavailable')
        bgr=np.frombuffer(pixels,dtype=np.uint8).reshape(self.camera.getHeight(),self.camera.getWidth(),4)[:,:,:3]
        ok,encoded=cv2.imencode('.png',bgr)
        if not ok:raise RuntimeError('image_encode_failed')
        self.seq+=1;self.last_image_sim=self.flight.elapsed_s
        self.images.append((self.flight.elapsed_s,time.monotonic(),time.time(),f'frame_{self.seq:06}',encoded.tobytes()))

    def capture(self):
        self.tick()
        self._expose()
        return self._observation(self.images[-1])

    def observe(self):
        threshold=self.flight.elapsed_s-self.config.image_delay_s
        sample=next((s for s in reversed(self.images) if s[0]<=threshold),self.images[0])
        return self._observation(sample,delayed=True)

    def _observation(self,sample,delayed=False):
        _,received,captured,identity,image=sample
        if delayed:received=min(received,time.monotonic()-self.config.image_delay_s)
        f=self.flight
        landed=(not f.flying and f.altitude_m<=LANDED_ALTITUDE_M and
                math.sqrt(sum(v*v for v in f.velocity))<=SETTLE_SPEED_MPS)
        return Observation(frame_id=identity,captured_at=captured,received_at=received,image_png=image,
                           battery_pct=self.battery,connected=self.connected,airborne=f.flying,landed=landed)

    def begin(self,action,identity):
        if self.active:raise RuntimeError('concurrent_command')
        self.result=None
        if action.kind=='speed':self.speed_cm_s=action.value
        self.active=CommandState(self.flight,action,identity,speed_cm_s=self.speed_cm_s,
            takeoff_height_m=self.config.simulated_takeoff_height_m,
            command_timeout_s=self.config.command_timeout_s,takeoff_timeout_s=self.config.takeoff_timeout_s,
            landing_timeout_s=self.config.landing_timeout_s)

    def keepalive(self):
        # No command goes on the wire in simulation: the private PID already
        # holds position between commands, so a heartbeat would be a fiction.
        # `keepalive_command` states that honestly in the trace; TelloBackend
        # overrides both with the real `rc 0 0 0 0`.
        return self.connected and (self.active is None or self.active.action.kind=='hold')

    keepalive_command = None

    def poll(self):
        result=self.result;self.result=None
        return result

    def stop_motion(self):
        self.active=None;self.result=None
        self.flight.hold_current()

    def close(self):
        if self.observe().landed:self.flight.stop()
