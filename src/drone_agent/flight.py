"""Rotor-level Webots flight controller, ported from Robot-Claw-v5."""

from math import atan2, cos, hypot, isfinite, pi, sin
from typing import Any, Optional, Tuple


K_VERTICAL_THRUST = 68.5
K_VERTICAL_P = 3.0
K_VERTICAL_I = 0.6
K_VERTICAL_LINEAR_P = 3.2
K_VERTICAL_D = 3.0
K_ROLL_P = 50.0
K_PITCH_P = 30.0
K_HORIZONTAL_I = 0.4
MAX_HORIZONTAL_INTEGRAL_M_S = 1.0
HORIZONTAL_INTEGRATION_RADIUS_M = 0.5
HORIZONTAL_INTEGRATION_SPEED_MPS = 0.15
MAX_FORWARD_DISTURBANCE = 2.0
MAX_LATERAL_DISTURBANCE = 1.0
MAX_YAW_DISTURBANCE = 1.3
POSITION_TOLERANCE_M = 0.15
TAKEOFF_TOLERANCE_M = 0.30
SETTLE_SPEED_MPS = 0.15
YAW_TOLERANCE_RAD = 5.0 * pi / 180.0
YAW_SETTLE_RATE_RAD_S = 3.0 * pi / 180.0
LINEAR_TIMEOUT_BASE_S = 8.0
LINEAR_TIMEOUT_PER_M = 4.0
ROTATION_TIMEOUT_BASE_S = 10.0
ROTATION_TIMEOUT_PER_RAD = 2.5
LANDED_ALTITUDE_M = 0.20


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _finite(value: float, fallback: float = 0.0) -> float:
    return float(value) if isfinite(value) else fallback


def normalise_angle(angle: float) -> float:
    return float(atan2(sin(angle), cos(angle)))


def navigation_heading(physical_yaw: float) -> float:
    return normalise_angle((pi / 2.0) - physical_yaw)


def body_frame_error(dx: float, dy: float, yaw: float) -> Tuple[float, float]:
    return (
        float(dx * sin(yaw) + dy * cos(yaw)),
        float(-dx * cos(yaw) + dy * sin(yaw)),
    )


def body_to_world(forward_m: float, left_m: float, yaw: float) -> Tuple[float, float]:
    return (
        float(forward_m * sin(yaw) - left_m * cos(yaw)),
        float(forward_m * cos(yaw) + left_m * sin(yaw)),
    )


class RotorFlightController:
    """Vertical PID, attitude loops, and position hold over four rotors."""

    def __init__(self, robot: Any, timestep_ms: int) -> None:
        self._robot = robot
        self._timestep_ms = int(timestep_ms)
        self._dt = self._timestep_ms / 1000.0
        self._imu = robot.getDevice("inertial unit")
        self._gps = robot.getDevice("gps")
        self._gyro = robot.getDevice("gyro")
        for device in (self._imu, self._gps, self._gyro):
            device.enable(self._timestep_ms)
        self._motors = []
        for name in (
            "front left propeller",
            "front right propeller",
            "rear left propeller",
            "rear right propeller",
        ):
            motor = robot.getDevice(name)
            motor.setPosition(float("inf"))
            motor.setVelocity(0.0)
            self._motors.append(motor)
        self.flying = False
        self.position = (0.0, 0.0, 0.0)
        self.velocity = (0.0, 0.0, 0.0)
        self.yaw = 0.0
        self.yaw_rate = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.on_step = None
        self.target_xy = (0.0, 0.0)
        self.target_altitude = 0.0
        self.target_yaw = 0.0
        self._alt_integral = 0.0
        self._xy_integral = (0.0, 0.0)
        self._elapsed_s = 0.0
        self.sensor_init_failed = False
        self._prime_sensors()

    @property
    def elapsed_s(self) -> float:
        return self._elapsed_s

    @property
    def altitude_m(self) -> float:
        return self.position[2]

    def _prime_sensors(self) -> None:
        for _ in range(20):
            if self._robot.step(self._timestep_ms) == -1:
                break
            self._elapsed_s += self._dt
            gps = self._gps.getValues()
            rpy = self._imu.getRollPitchYaw()
            if all(isfinite(value) for value in tuple(gps) + tuple(rpy)):
                self.position = tuple(float(value) for value in gps)
                self.target_xy = self.position[:2]
                self.target_altitude = self.position[2]
                self.yaw = navigation_heading(float(rpy[2]))
                self.roll = float(rpy[0])
                self.pitch = float(rpy[1])
                self.target_yaw = self.yaw
                return
        self.sensor_init_failed = True

    def _read_sensors(self) -> None:
        gps = self._gps.getValues()
        if all(isfinite(value) for value in gps):
            previous = self.position
            self.position = tuple(float(value) for value in gps)
            self.velocity = tuple(
                (self.position[index] - previous[index]) / self._dt for index in range(3)
            )
        rpy = self._imu.getRollPitchYaw()
        self.roll = _finite(rpy[0], self.roll)
        self.pitch = _finite(rpy[1], self.pitch)
        self.yaw = navigation_heading(_finite(rpy[2], self.yaw))
        rates = self._gyro.getValues()
        self.yaw_rate = _finite(rates[2], self.yaw_rate)

    def tick(self) -> None:
        self._read_sensors()
        roll, pitch, _ = self._imu.getRollPitchYaw()
        roll_rate, pitch_rate, _ = self._gyro.getValues()
        if not self.flying:
            self.clear_integrals()
            for motor in self._motors:
                motor.setVelocity(0.0)
            return
        dx = self.target_xy[0] - self.position[0]
        dy = self.target_xy[1] - self.position[1]
        if (self.altitude_m > LANDED_ALTITUDE_M
                and hypot(dx, dy) <= HORIZONTAL_INTEGRATION_RADIUS_M
                and hypot(*self.velocity[:2]) <= HORIZONTAL_INTEGRATION_SPEED_MPS):
            integral = tuple(value + error * self._dt
                             for value, error in zip(self._xy_integral, (dx, dy)))
            scale = max(1.0, hypot(*integral) / MAX_HORIZONTAL_INTEGRAL_M_S)
            self._xy_integral = tuple(value / scale for value in integral)
        forward_error, left_error = body_frame_error(dx, dy, self.yaw)
        forward_integral, left_integral = body_frame_error(*self._xy_integral, self.yaw)
        pitch_disturbance = clamp(
            -2.0 * forward_error - K_HORIZONTAL_I * forward_integral,
            -MAX_FORWARD_DISTURBANCE, MAX_FORWARD_DISTURBANCE
        )
        roll_disturbance = clamp(
            2.0 * left_error + K_HORIZONTAL_I * left_integral,
            -MAX_LATERAL_DISTURBANCE, MAX_LATERAL_DISTURBANCE
        )
        yaw_error = normalise_angle(self.yaw - self.target_yaw)
        yaw_input = clamp(
            2.0 * yaw_error, -MAX_YAW_DISTURBANCE, MAX_YAW_DISTURBANCE
        )
        roll_input = (
            K_ROLL_P * clamp(_finite(roll), -1.0, 1.0)
            + _finite(roll_rate)
            + roll_disturbance
        )
        pitch_input = (
            K_PITCH_P * clamp(_finite(pitch), -1.0, 1.0)
            + _finite(pitch_rate)
            + pitch_disturbance
        )
        altitude_error = clamp(self.target_altitude - self.position[2], -1.0, 1.0)
        if abs(altitude_error) < 0.5:
            self._alt_integral = clamp(
                self._alt_integral + altitude_error * self._dt, -2.0, 2.0
            )
        vertical_input = (
            K_VERTICAL_P * pow(altitude_error, 3.0)
            + K_VERTICAL_LINEAR_P * altitude_error
            + K_VERTICAL_I * self._alt_integral
            - K_VERTICAL_D * self.velocity[2]
        )
        base = K_VERTICAL_THRUST + vertical_input
        inputs = (
            base - roll_input + pitch_input - yaw_input,
            base + roll_input + pitch_input + yaw_input,
            base - roll_input - pitch_input + yaw_input,
            base + roll_input - pitch_input - yaw_input,
        )
        if not all(isfinite(value) for value in inputs):
            return
        self._motors[0].setVelocity(inputs[0])
        self._motors[1].setVelocity(-inputs[1])
        self._motors[2].setVelocity(-inputs[2])
        self._motors[3].setVelocity(inputs[3])

    def step(self) -> bool:
        """Advance the simulation one timestep. False means Webots stepped out."""
        if self._robot.step(self._timestep_ms) == -1:
            return False
        self._elapsed_s += self._dt
        self.tick()
        if self.on_step is not None:
            self.on_step()
        return True

    def set_target(self, *, xy=None, altitude=None, yaw=None) -> None:
        """Aim the PID. Omitted arguments keep their current target.

        The caller is responsible for supplying targets in this controller's
        own frame: xy and altitude in metres, yaw in the navigation-heading
        convention produced by `navigation_heading`.
        """
        if xy is not None:
            self.target_xy = tuple(xy)
        if altitude is not None:
            self.target_altitude = float(altitude)
        if yaw is not None:
            self.target_yaw = float(yaw)

    def hold_current(self) -> None:
        """Target wherever the aircraft is now, cancelling any pending leg."""
        self.set_target(xy=self.position[:2], altitude=self.altitude_m, yaw=self.yaw)

    def clear_integrals(self) -> None:
        """Reset vertical and horizontal compensation for a fresh flight."""
        self._alt_integral = 0.0
        self._xy_integral = (0.0, 0.0)

    def linear_reached(self, tolerance: float) -> bool:
        """True when xy and altitude are within `tolerance` and the body is settled."""
        dx = self.target_xy[0] - self.position[0]
        dy = self.target_xy[1] - self.position[1]
        xy_error = (dx * dx + dy * dy) ** 0.5
        altitude_error = abs(self.target_altitude - self.position[2])
        speed = sum(value * value for value in self.velocity) ** 0.5
        return (xy_error <= tolerance and altitude_error <= tolerance
                and speed <= SETTLE_SPEED_MPS)

    def yaw_reached(self, tolerance_rad: float = YAW_TOLERANCE_RAD) -> bool:
        """True when the heading is within tolerance and the yaw rate has settled."""
        error = abs(normalise_angle(self.target_yaw - self.yaw))
        return error <= tolerance_rad and abs(self.yaw_rate) <= YAW_SETTLE_RATE_RAD_S

    def stop(self) -> None:
        self.flying = False
        self.clear_integrals()
        for motor in self._motors:
            motor.setVelocity(0.0)
