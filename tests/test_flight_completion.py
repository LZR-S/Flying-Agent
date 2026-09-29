import math
from types import MethodType, SimpleNamespace

import pytest

from backends import FakeFlight
from drone_agent.flight import RotorFlightController
from drone_agent.protocol import Action
from drone_agent.webots_backend import CommandState


def takeoff_at(position, velocity=(0., 0., 0.)):
    flight = FakeFlight(position=(0., 0., .07))
    flight.linear_reached = MethodType(RotorFlightController.linear_reached, flight)
    command = CommandState(flight, Action(kind='takeoff'), 'takeoff')
    flight.position = position
    flight.altitude_m = position[2]
    flight.velocity = velocity
    flight.elapsed_s = 10.
    assert command.poll() is None
    flight.elapsed_s += .6
    return command.poll()


def test_takeoff_accepts_stable_height_with_bounded_horizontal_drift():
    result = takeoff_at((.077, -.032, .996))
    assert result is not None and result.status == 'completed'


@pytest.mark.parametrize('position,velocity', [
    ((.16, 0., 1.), (0., 0., 0.)),
    ((0., 0., .8), (0., 0., 0.)),
    ((0., 0., 1.), (.06, 0., 0.)),
    ((0., 0., .07), (0., 0., 0.)),
])
def test_takeoff_rejects_drift_wrong_height_motion_and_ground(position, velocity):
    assert takeoff_at(position, velocity) is None


def controller():
    flight = RotorFlightController.__new__(RotorFlightController)
    flight._dt = .016
    flight.flying = True
    flight.position = (0., 0., 1.)
    flight.velocity = (0., 0., 0.)
    flight.target_xy = (.08, 0.)
    flight.target_altitude = 1.
    flight.target_yaw = flight.yaw = math.pi / 2
    flight._alt_integral = 0.
    flight._xy_integral = (0., 0.)
    flight._imu = SimpleNamespace(getRollPitchYaw=lambda: (0., 0., 0.))
    flight._gyro = SimpleNamespace(getValues=lambda: (0., 0., 0.))
    flight._read_sensors = lambda: None
    flight._motors = [SimpleNamespace(setVelocity=lambda value: None) for _ in range(4)]
    speeds = [0.] * 4
    for i, motor in enumerate(flight._motors):
        motor.setVelocity = lambda value, index=i: speeds.__setitem__(index, value)
    return flight, speeds


def pitch_effort(speeds):
    a, b, c, d = (abs(v) for v in speeds)
    return (a + b - c - d) / 4


def test_stationary_horizontal_error_accumulates_corrective_effort():
    flight, speeds = controller()
    flight.tick()
    initial = pitch_effort(speeds)
    for _ in range(300):
        flight.tick()
    assert pitch_effort(speeds) < initial - .05
    assert flight._xy_integral[0] > 0.


def test_horizontal_integral_is_bounded_and_unwinds():
    flight, speeds = controller()
    for _ in range(3000):
        flight.tick()
    saturated = pitch_effort(speeds)
    integral = flight._xy_integral
    assert integral[0] > 0.
    for _ in range(3000):
        flight.tick()
    assert flight._xy_integral == pytest.approx(integral)
    assert pitch_effort(speeds) == pytest.approx(saturated)
    flight.target_xy = (-.08, 0.)
    for _ in range(100):
        flight.tick()
    assert flight._xy_integral[0] < integral[0]


@pytest.mark.parametrize('altitude,speed,distance', [(.07, 0., .08), (1., .5, .08), (1., 0., 3.)])
def test_horizontal_integral_does_not_wind_up_on_ground_or_during_transit(altitude, speed, distance):
    flight, _ = controller()
    flight.position = (0., 0., altitude)
    flight.velocity = (speed, 0., 0.)
    flight.target_xy = (distance, 0.)
    for _ in range(100):
        flight.tick()
    assert flight._xy_integral == (0., 0.)


def test_new_takeoff_and_motor_stop_reset_horizontal_compensation():
    flight, _ = controller()
    flight._xy_integral = (.2, -.1)
    flight.clear_integrals()
    assert flight._xy_integral == (0., 0.)
    flight._xy_integral = (.2, -.1)
    flight.stop()
    assert flight._xy_integral == (0., 0.)


def test_stationary_offset_does_not_satisfy_small_horizontal_translation():
    flight = FakeFlight(position=(0., 0., 1.), yaw=math.pi / 2)
    flight.linear_reached = MethodType(RotorFlightController.linear_reached, flight)
    command = CommandState(flight, Action(kind='forward', value=20), 'forward')
    flight.position = (.05, 0., 1.)
    flight.elapsed_s = 10.
    assert command.poll() is None
    flight.elapsed_s = 11.
    assert command.poll() is None
