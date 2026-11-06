"""Two cameras as one hand source.

Each camera has its own thread that grabs a frame, mirrors it and runs hand tracking, so the two trackers work in parallel.
The control loop is paced by ONE camera (camera 1, or camera 2 if camera 1 stops delivering), exactly as with a single camera,
so every frame-counting setting (hold frames etc.) keeps its meaning. On each step the newest observation from each camera is
handed to the Fuser (fusion.py), which returns the fused hand.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2

from .fusion import Fuser, Observation


@dataclass
class Step:
    frame: object                # the pacing camera's mirrored picture (draw on this)
    t: float                     # when it was captured
    det: tuple | None            # (raw landmarks of the best view, label, fused landmarks for the controller) or None
    inset: list                  # [(mirrored frame, that camera's own landmarks or None)] for the other camera(s)
    mode: str                    # "fused" | "camera 1 only" | "camera 2 only" | "learning NN%" | "no hand"
    best: int


class _Worker:
    def __init__(self, camera, tracker):
        self.camera, self.tracker = camera, tracker
        self.cond = threading.Condition()
        self.seq = 0
        self.frame = None
        self.t = 0.0
        self.det = None
        self._stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def alive(self) -> bool:
        return self.camera.alive

    def _run(self) -> None:
        while not self._stop:
            got = self.camera.read(timeout=0.5)
            if got is None:
                if not self.camera.alive:
                    break
                continue
            frame, t = got
            frame = cv2.flip(frame, 1)
            try:
                det = self.tracker.detect(frame, int(t * 1000))
            except Exception:
                det = None
            with self.cond:
                self.frame, self.t, self.det = frame, t, det
                self.seq += 1
                self.cond.notify_all()
        with self.cond:
            self.cond.notify_all()

    def snapshot(self):
        with self.cond:
            return self.seq, self.frame, self.t, self.det

    def stop(self) -> None:
        self._stop = True


def _observation(snap):
    seq, frame, t, det = snap
    if frame is None or det is None:
        return None
    lm, label = det[0], det[1]
    score = det[2] if len(det) > 2 else 1.0
    return Observation(t=t, lm=lm, label=label, score=score)


class MultiSource:
    """workers: [(camera, tracker), (camera, tracker)] (camera 1 first). Fuser may be injected for tests."""

    def __init__(self, pairs, fuser: Fuser | None = None, stale_driver_s: float = 0.4):
        self.workers = [_Worker(c, t) for c, t in pairs]
        self.fuser = fuser or Fuser()
        self.stale_driver_s = stale_driver_s
        self._seen = [0] * len(self.workers)
        self._driver = 0

    @property
    def alive(self) -> bool:
        return any(w.alive for w in self.workers)

    def _pick_driver(self) -> int:
        w0 = self.workers[0]
        if w0.alive and (self.workers[0].t == 0.0 or time.monotonic() - w0.t < self.stale_driver_s):
            return 0
        return 1 if len(self.workers) > 1 and self.workers[1].alive else 0

    def read(self, timeout: float = 0.5):
        """Wait for the next picture from the pacing camera, fuse, and return a Step (or None on timeout / no cameras)."""
        d = self._driver = self._pick_driver()
        w = self.workers[d]
        with w.cond:
            if not w.cond.wait_for(lambda: w.seq != self._seen[d] or not w.alive, timeout) or w.seq == self._seen[d]:
                return None
            self._seen[d] = w.seq
        snaps = [x.snapshot() for x in self.workers]
        obs = [_observation(s) for s in snaps]
        t = snaps[d][2]
        a, b = (obs[0], obs[1]) if len(obs) > 1 else (obs[0], None)
        fused = self.fuser.update(a, b, t)
        frame = snaps[d][1]
        inset = [(snaps[i][1], obs[i].lm if obs[i] else None) for i in range(len(snaps)) if i != d and snaps[i][1] is not None]
        if fused is None:
            return Step(frame, t, None, inset, "no hand", self.fuser.best)
        return Step(frame, t, (fused.raw, fused.label, fused.lm), inset, fused.mode, fused.best)

    def release(self) -> None:
        for w in self.workers:
            w.stop()
            w.camera.release()
