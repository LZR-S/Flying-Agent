"""Bounded, asynchronous public preview; never acquires sensors or archives evidence."""
import copy
import queue
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from .artifacts import write_json
from .viewfinder import render_viewfinder


class PreviewWriter:
    def __init__(self, directory, fps=8):
        self.directory = Path(directory)
        self.interval = 1 / fps
        self.next_at = 0.
        self.last_id = None
        self.error = None
        self.queue = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name='dashboard-preview', daemon=True)
        self.thread.start()

    def offer(self, observation, photo_frame):
        now = time.monotonic()
        identity=(observation.frame_id,photo_frame['version'])
        if self.stopped.is_set() or self.error or now < self.next_at or identity == self.last_id:
            return
        self.next_at = now + self.interval
        self.last_id = identity
        item = (observation.image_png, observation.public(now), copy.deepcopy(photo_frame))
        try:
            self.queue.get_nowait()
        except queue.Empty:
            pass
        self.queue.put_nowait(item)

    def _run(self):
        retained = []
        while not self.stopped.is_set():
            try:
                png, observation, frame = self.queue.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                pixels = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
                if pixels is None:
                    raise ValueError('invalid_preview')
                folder = self.directory/'live'
                folder.mkdir(exist_ok=True)
                identity = observation['frame_id']
                image_path = f'live/{identity}-v{frame["version"]}.jpg'
                photo_path = None
                viewfinder_path = None
                paths = [image_path]
                self._jpeg(self.directory/image_path, pixels)
                rectangle = frame['rectangle']
                if rectangle is not None:
                    x,y,w,h = (rectangle[k] for k in ('left','top','width','height'))
                    photo_path = f'live/{identity}-photo-v{frame["version"]}.jpg'
                    self._jpeg(self.directory/photo_path, pixels[y:y+h,x:x+w])
                    paths.append(photo_path)
                    viewfinder_path=f'live/{identity}-viewfinder-v{frame["version"]}.jpg'
                    self._jpeg(self.directory/viewfinder_path,render_viewfinder(pixels,frame))
                    paths.append(viewfinder_path)
                write_json(self.directory/'preview.json', {
                    'frame_id':identity,'captured_at':observation['captured_at'],
                    'published_at':time.time(),'image_path':image_path,'photo_path':photo_path,'viewfinder_path':viewfinder_path,
                    'observation':observation,'photo_frame':frame,
                })
                retained.append(paths)
                if len(retained) > 24:
                    for path in retained.pop(0):
                        (self.directory/path).unlink(missing_ok=True)
            except Exception as error:
                self.error = type(error).__name__
                return

    @staticmethod
    def _jpeg(path, pixels):
        ok, data = cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY,85])
        if not ok:
            raise OSError('preview_encode_failed')
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(data.tobytes())
        temporary.replace(path)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=1)
