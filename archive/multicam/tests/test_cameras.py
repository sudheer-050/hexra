import numpy as np

from gesture_control.cameras import MultiCamera, scan_cameras


class FakeCap:
    def __init__(self, available, shape=(480, 640, 3)):
        self.available, self.shape = available, shape

    def isOpened(self):
        return self.available

    def read(self):
        return (True, np.zeros(self.shape, np.uint8)) if self.available else (False, None)

    def release(self):
        pass


def opener_for(present):
    return lambda i: FakeCap(i in present)


def test_scan_finds_every_connected_camera():
    assert [c["index"] for c in scan_cameras(opener=opener_for({0, 1, 2}))] == [0, 1, 2]


def test_scan_tolerates_one_gap_but_stops_after_two_misses():
    assert [c["index"] for c in scan_cameras(opener=opener_for({0, 2}))] == [0, 2]       # index 1 missing
    assert [c["index"] for c in scan_cameras(opener=opener_for({0, 5}))] == [0]          # two misses end the scan


def test_scan_with_no_cameras_and_with_one():
    assert scan_cameras(opener=opener_for(set())) == []
    assert len(scan_cameras(opener=opener_for({0}))) == 1


def test_scan_reports_resolution():
    found = scan_cameras(opener=lambda i: FakeCap(i == 0, (720, 1280, 3)))
    assert (found[0]["width"], found[0]["height"]) == (1280, 720)


class FakeCam:
    def __init__(self, index, w=640, h=480, ts=1.0, alive=True):
        self.index, self.ts, self.alive, self.opened = index, ts, alive, True

    def read(self, timeout=0.5):
        return f"frame{self.index}", self.ts

    def latest(self):
        return f"frame{self.index}", self.ts

    def release(self):
        pass


def test_multicamera_reads_all_in_sync_and_drops_stale_ones():
    cams = {0: FakeCam(0, ts=1.00), 1: FakeCam(1, ts=1.02), 2: FakeCam(2, ts=0.50)}   # camera 2 is 0.5 s behind
    mc = MultiCamera([0, 1, 2], factory=lambda i, w, h: cams[i])
    frames, t = mc.read()
    assert set(frames) == {0, 1} and t == 1.00


def test_multicamera_skips_cameras_that_died():
    cams = {0: FakeCam(0, ts=1.0), 1: FakeCam(1, ts=1.0, alive=False)}
    mc = MultiCamera([0, 1], factory=lambda i, w, h: cams[i])
    assert set(mc.read()[0]) == {0}
