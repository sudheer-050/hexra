"""Shows the camera preview on its own thread, so drawing never makes the control loop wait.

imshow + waitKey can take 5-20 ms. Done inline, a camera frame that arrives during that time sits waiting, which adds
up to that much delay to the cursor. Here the control loop only hands over the newest picture and moves on.
"""
from __future__ import annotations

import queue
import threading

import cv2

from . import icon


class Display:
    def __init__(self, title: str):
        self.title = title
        self._cond = threading.Condition()
        self._frame = None
        self._stop = False
        self._keys: queue.SimpleQueue = queue.SimpleQueue()
        self._icon_done = False
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
                if not self._icon_done:                  # the window exists now: give it the Hexra icon (title bar and taskbar)
                    self._icon_done = True
                    icon.apply_to_window(self.title)
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


class FilePreview:
    """Same interface as Display, but instead of a window it writes the newest picture to data/preview.jpg for the settings window.

    JPEG encoding happens on this thread, never in the control loop, and at most ~20 pictures a second are written.
    """

    def __init__(self, base, quality: int = 72, max_fps: float = 20.0):
        from . import ipc

        self._ipc, self._path = ipc, base / ipc.PREVIEW
        self._quality, self._gap = quality, 1.0 / max_fps
        self._cond = threading.Condition()
        self._frame = None
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def show(self, frame) -> None:
        with self._cond:
            self._frame = frame
            self._cond.notify()

    def keys(self) -> list:
        return []

    def _run(self) -> None:
        import time

        last = 0.0
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._frame is not None or self._stop, 0.2)
                if self._stop:
                    break
                frame, self._frame = self._frame, None
            if frame is None or time.monotonic() - last < self._gap:
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
            if ok:
                self._ipc.write_atomic(self._path, buf.tobytes())
                last = time.monotonic()

    def close(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        self._thread.join(timeout=1.0)
