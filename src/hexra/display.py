"""Shows the camera preview on its own thread, so drawing never makes the control loop wait.

imshow + waitKey can take 5-20 ms. Done inline, a camera frame that arrives during that time sits waiting, which adds
up to that much delay to the cursor. Here the control loop only hands over the newest picture and moves on.
"""
from __future__ import annotations

import queue
import threading

import cv2


class Display:
    def __init__(self, title: str):
        self.title = title
        self._cond = threading.Condition()
        self._frame = None
        self._stop = False
        self._keys: queue.SimpleQueue = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def show(self, frame) -> None:
        """Give the window the newest picture (older, not-yet-shown ones are dropped)."""
        with self._cond:
            self._frame = frame
            self._cond.notify()

    def keys(self) -> list:
        """Key codes pressed in the window since the last call."""
        out = []
        while True:
            try:
                out.append(self._keys.get_nowait())
            except queue.Empty:
                return out

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._frame is not None or self._stop, 0.05)
                if self._stop:
                    break
                frame, self._frame = self._frame, None
            if frame is not None:
                cv2.imshow(self.title, frame)
            key = cv2.waitKey(1) & 0xFF
            if key != 255:
                self._keys.put(key)
        try:
            cv2.destroyWindow(self.title)
        except cv2.error:
            pass

    def close(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        self._thread.join(timeout=1.0)
