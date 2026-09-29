"""Exercise the installed SDK with networking disabled, including its receivers."""
import threading
from unittest.mock import Mock

import numpy as np
import pytest

pytest.importorskip('djitellopy')
from drone_agent.tello_io import ManagedTello, TimedFrameReader, StateMailbox
from djitellopy import tello as sdk_module


def test_sensor_timestamps_change_on_publication_only(monkeypatch):
    from drone_agent import tello_io
    now = [10.]
    monkeypatch.setattr(tello_io.time, 'monotonic', lambda: now[0])
    mailbox = StateMailbox({'responses': [], 'state': {}})
    state = {'h': 0, 'tof': 5}
    mailbox['state'] = state
    first = mailbox.sample()
    now[0] = 20.
    assert mailbox.sample() == first
    mailbox['state'] = dict(state)
    assert mailbox.sample()[0] > first[0]
    assert mailbox.sample()[1] == 20.

    reader = TimedFrameReader.__new__(TimedFrameReader)
    reader.lock = threading.Lock()
    reader.sequence = 0
    reader.latest = None
    reader.initializing = False
    pixels = np.zeros((720, 960, 3), np.uint8)
    reader.frame = pixels
    first = reader.sample()
    now[0] = 30.
    assert reader.sample() is first
    reader.frame = pixels.copy()
    second = reader.sample()
    assert second[0] > first[0] and second[1] == 30.


def test_real_sdk_creation_closes_without_network_or_implicit_land(monkeypatch):
    wire = Mock()
    monkeypatch.setattr(sdk_module, 'threads_initialized', True)
    monkeypatch.setattr(sdk_module, 'client_socket', wire, raising=False)
    monkeypatch.setattr(sdk_module, 'drones', {})
    aircraft = ManagedTello(host='192.0.2.1')
    assert aircraft.retry_count == 1
    assert aircraft.state_sample() is None
    aircraft.send_command_without_return('forward 50')
    assert [c.args[0] for c in wire.sendto.call_args_list] == [b'forward 50']
    aircraft.is_flying = True
    aircraft.close_link()
    aircraft.end()
    assert wire.sendto.call_count == 1


def test_real_sdk_control_method_does_not_retry(monkeypatch):
    monkeypatch.setattr(sdk_module, 'threads_initialized', True)
    monkeypatch.setattr(sdk_module, 'drones', {})
    aircraft = ManagedTello(host='192.0.2.1')
    send = Mock(return_value='timeout')
    monkeypatch.setattr(aircraft, 'send_command_with_return', send)
    with pytest.raises(Exception): aircraft.move_forward(50)
    assert send.call_count == 1
    aircraft.close_link()


def test_backend_timeout_uses_real_sdk_wire_once_and_ignores_late_ack(monkeypatch):
    from drone_agent.protocol import Action, Config
    from drone_agent.tello_backend import TelloBackend
    from drone_agent import tello_io
    now = [100.]
    monkeypatch.setattr(tello_io.time, 'monotonic', lambda: now[0])
    wire = Mock()
    monkeypatch.setattr(sdk_module, 'threads_initialized', True)
    monkeypatch.setattr(sdk_module, 'client_socket', wire, raising=False)
    monkeypatch.setattr(sdk_module, 'drones', {})
    aircraft = ManagedTello(host='192.0.2.1')
    monkeypatch.setattr(aircraft, 'connect', lambda: None)
    monkeypatch.setattr(aircraft, 'set_speed', lambda _: None)
    monkeypatch.setattr(aircraft, 'streamon', lambda: None)
    reader = TimedFrameReader.__new__(TimedFrameReader)
    reader.lock = threading.Lock(); reader.sequence = 0; reader.latest = None; reader.initializing = False
    reader.frame = np.zeros((720,960,3),np.uint8)
    aircraft.background_frame_read = reader
    state = {'h':150,'tof':150,'bat':90,'yaw':0,'vgx':0,'vgy':0,'vgz':0,'roll':0,'pitch':0}
    aircraft.get_own_udp_object()['state'] = state
    backend = TelloBackend(aircraft,Config(command_timeout_s=.1),clock=lambda:now[0])
    backend.connect()
    backend.begin(Action(kind='forward',value=50),'move')
    now[0] += .2; backend.tick()
    assert backend.poll().status == 'unknown'
    backend.stop_motion(); backend.begin(Action(kind='land'),'land')
    aircraft.get_own_udp_object()['responses'].append(b'ok')
    backend.tick()
    assert backend.poll() is None
    assert [c.args[0] for c in wire.sendto.call_args_list] == [b'forward 50',b'stop',b'land']
    backend.close()
