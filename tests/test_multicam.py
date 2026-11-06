"""The two-camera source with fake cameras and trackers: pacing, parallel tracking, failover, no camera needed."""
import time
from types import SimpleNamespace

import numpy as np

from hexra.multicam import MultiSource
from tests.test_fusion import M_TRUE, make_lm, to_cam2, truth


class FakeCamera:
    """Delivers numbered frames at `fps` until killed; the frame's pixel [0,0,0] carries its number."""

    def __init__(self, fps=60):
        self.fps, self.alive, self.n, self.t0 = fps, True, 0, time.monotonic()

    def read(self, timeout=0.5):
        time.sleep(1 / self.fps)
        if not self.alive:
            return None
        self.n += 1
        frame = np.zeros((48, 64, 3), np.uint8)
        frame[0, 0, 0] = self.n % 250
        return frame, time.monotonic()

    def release(self):
        self.alive = False


class FakeTracker:
    """Sees the hand at a position that follows the global time, in this camera's own coordinates."""

    def __init__(self, second=False, sees=True):
        self.second, self.sees = second, sees

    def detect(self, frame, ts_ms):
        if not self.sees:
            return None
        p = truth(ts_ms / 1000 * 30)
        return make_lm(to_cam2(p) if self.second else p), "Right", 0.95


def make(sees0=True, sees1=True, fps0=60, fps1=60):
    c0, c1 = FakeCamera(fps0), FakeCamera(fps1)
    return MultiSource([(c0, FakeTracker(False, sees0)), (c1, FakeTracker(True, sees1))]), c0, c1


def run(src, seconds):
    out, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        s = src.read(timeout=0.5)
        if s is not None:
            out.append(s)
    return out


def test_it_is_paced_by_camera_1_and_returns_the_fused_hand():
    src, c0, c1 = make()
    try:
        steps = run(src, 6.0)
    finally:
        src.release()
    assert len(steps) > 60
    assert steps[-1].mode == "fused" and steps[-1].det is not None
    raw, label, lm = steps[-1].det
    assert label == "Right" and len(lm) == 21 and steps[-1].inset                      # the other camera's picture is there for the preview
    # the number of steps follows camera 1's frames, not the sum of both cameras
    assert len(steps) <= c0.n + 2


def test_when_camera_1_stops_seeing_the_hand_camera_2_carries_on():
    src, c0, c1 = make()
    try:
        run(src, 6.0)
        src.workers[0].tracker.sees = False
        steps = run(src, 1.0)
    finally:
        src.release()
    assert steps[-1].mode == "camera 2 only" and steps[-1].det is not None


def test_when_camera_1_dies_camera_2_paces_the_loop_and_nothing_crashes():
    src, c0, c1 = make()
    try:
        run(src, 2.0)
        c0.alive = False
        steps = run(src, 1.5)
        still_alive = src.alive
    finally:
        src.release()
    assert any(s.mode == "camera 2 only" for s in steps[-20:])
    assert still_alive


def test_no_hand_anywhere_gives_no_detection_but_keeps_stepping():
    src, c0, c1 = make(sees0=False, sees1=False)
    try:
        steps = run(src, 1.0)
    finally:
        src.release()
    assert steps and all(s.det is None and s.mode == "no hand" for s in steps)


def test_release_stops_both_cameras():
    src, c0, c1 = make()
    src.release()
    assert not c0.alive and not c1.alive
