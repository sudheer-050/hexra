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


def probe_cameras(max_index: int = 4, thumb=(160, 120)) -> list:
    """Find the cameras Windows offers (indices 0, 1, 2... stop at the first that does not open) with a small picture of each,
    so the user can tell which is which. Only call this while Hexra is not using a camera: one that is busy cannot be opened."""
    import base64

    found = []
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i)
        if not cap.isOpened():
            cap.release()
            break
        frame = None
        for _ in range(6):                      # the first frames of a camera that has just opened are often black
            ok, f = cap.read()
            if ok:
                frame = f
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        item = {"index": i, "width": w, "height": h, "thumb": ""}
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", cv2.resize(frame, thumb), [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                item["thumb"] = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
        found.append(item)
    return found
