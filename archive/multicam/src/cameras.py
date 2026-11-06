"""Find every connected camera and read several of them together."""
from __future__ import annotations

import cv2

from .camera import ThreadedCamera


def scan_cameras(max_index: int = 8, stop_after_misses: int = 2, opener=cv2.VideoCapture) -> list:
    """Try camera indices 0, 1, 2, ... and return [{"index", "width", "height"}, ...] for the ones that deliver a frame.

    Stops after `stop_after_misses` empty indices in a row (opening a missing camera can be slow on Windows).
    """
    found, misses = [], 0
    for i in range(max_index):
        cap = opener(i)
        ok, frame = False, None
        try:
            if cap.isOpened():
                ok, frame = cap.read()
        finally:
            cap.release()
        if ok and frame is not None:
            found.append({"index": i, "width": int(frame.shape[1]), "height": int(frame.shape[0])})
            misses = 0
        else:
            misses += 1
            if misses >= stop_after_misses:
                break
    return found


class MultiCamera:
    """Several cameras read in the background. read() waits for the PRIMARY camera's next frame, then takes the
    newest frame from every other camera, dropping any that is too far out of sync to triangulate with."""

    def __init__(self, indices, width: int = 640, height: int = 480, max_skew_s: float = 0.06, factory=ThreadedCamera):
        self.indices = list(indices)
        self.primary = self.indices[0]
        self.max_skew_s = max_skew_s
        self.cams = {i: factory(i, width, height) for i in self.indices}

    @property
    def opened(self) -> bool:
        return all(c.opened for c in self.cams.values())

    @property
    def alive(self) -> bool:
        return self.cams[self.primary].alive

    def read(self, timeout: float = 0.5):
        """Return ({camera_index: frame}, capture_time_of_primary_frame), or None on timeout."""
        got = self.cams[self.primary].read(timeout)
        if got is None:
            return None
        frame0, t0 = got
        frames = {self.primary: frame0}
        for i, cam in self.cams.items():
            if i == self.primary or not cam.alive:
                continue
            lat = cam.latest()
            if lat is not None and abs(lat[1] - t0) <= self.max_skew_s:
                frames[i] = lat[0]
        return frames, t0

    def release(self) -> None:
        for cam in self.cams.values():
            cam.release()
