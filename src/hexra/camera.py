"""Low-latency webcam reader.

A background thread reads the camera continuously and keeps only the NEWEST frame, so the main loop never
processes stale buffered frames (a common source of 100 ms+ lag). read() waits for a frame newer than the
last one it returned, and also returns the moment that frame was captured.
"""
from __future__ import annotations

import threading
import time

import cv2


class ThreadedCamera:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self._cap = cv2.VideoCapture(index)
        self.opened = self._cap.isOpened()
        if self.opened:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cond = threading.Condition()
        self._frame = None
        self._ts = 0.0
        self._seq = 0
        self._last_seq = 0
        self._stop = False
        self.alive = self.opened
        if self.opened:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        fails = 0
        while not self._stop:
            ok, frame = self._cap.read()
            if not ok:
                fails += 1
                if fails > 50:
                    break
                time.sleep(0.01)
                continue
            fails = 0
            with self._cond:
                self._frame, self._ts, self._seq = frame, time.monotonic(), self._seq + 1
                self._cond.notify_all()
        self.alive = False
        with self._cond:
            self._cond.notify_all()

    def latest(self):
        """(frame, captured_at) of the newest frame so far, without waiting. None before the first frame."""
        with self._cond:
            return None if self._frame is None else (self._frame, self._ts)

    def read(self, timeout: float = 0.5):
        """Return (frame, captured_at) for the newest unseen frame, or None on timeout / camera failure."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._seq != self._last_seq or not self.alive, timeout):
                return None
            if self._seq == self._last_seq:
                return None
            self._last_seq = self._seq
            return self._frame, self._ts

    def release(self) -> None:
        self._stop = True
        time.sleep(0.05)
        self._cap.release()
