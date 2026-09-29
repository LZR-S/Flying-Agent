"""DJITelloPy 2.5.0 receiver hooks. Import only for the optional hardware backend.

The SDK exposes decoded pixels and parsed state without timestamps. Timestamp
publication at those two receiver boundaries, never when the agent reads them.
Tello does not supply a camera exposure clock: captured_at is host decode time.
"""
import threading
import time

from djitellopy import BackgroundFrameRead, Tello
from djitellopy import tello as sdk_module


class StateMailbox(dict):
    def __init__(self, values):
        super().__init__(values)
        self.lock = threading.Lock()
        self.sequence = 0
        self.latest = None

    def __setitem__(self, key, value):
        if key != 'state':
            return super().__setitem__(key, value)
        with self.lock:
            super().__setitem__(key, value)
            if value:
                self.sequence += 1
                self.latest = (self.sequence, time.monotonic(), dict(value))

    def sample(self):
        with self.lock:
            return self.latest


class TimedFrameReader(BackgroundFrameRead):
    def __init__(self, tello, address):
        self.sequence = 0
        self.latest = None
        self.initializing = True
        super().__init__(tello, address)
        self.initializing = False

    @property
    def frame(self):
        with self.lock:
            return self._frame

    @frame.setter
    def frame(self, value):
        with self.lock:
            self._frame = value
            # The SDK constructor installs a 400x300 black placeholder.
            if not self.initializing:
                self.sequence += 1
                self.latest = (self.sequence, time.monotonic(), time.time(), value)

    def sample(self):
        with self.lock:
            return self.latest


class ManagedTello(Tello):
    """Keep SDK transport/decoding, disable retries and implicit teardown flights."""
    def __init__(self, host):
        self._link_closed = False
        super().__init__(host=host, retry_count=1)
        self._mailbox = StateMailbox(self.get_own_udp_object())
        sdk_module.drones[host] = self._mailbox

    def state_sample(self):
        return self._mailbox.sample()

    def frame_sample(self):
        reader = self.background_frame_read
        return None if reader is None else reader.sample()

    def get_frame_read(self):
        if self.background_frame_read is None:
            self.background_frame_read = TimedFrameReader(self, self.get_udp_video_address())
            self.background_frame_read.start()
        return self.background_frame_read

    def close_link(self):
        if self._link_closed:
            return
        self._link_closed = True
        reader = self.background_frame_read
        if reader is not None:
            reader.stop()
        sdk_module.drones.pop(self.address[0], None)

    def end(self):
        # Tello.__del__ calls end(); its default implementation can issue land.
        self.close_link()
