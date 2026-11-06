"""The first-run calibration: Hexra asks for each pose in turn and records what YOUR hand does.

A pure state machine (no camera, no window), so it is fully testable: feed it one hand-feature vector per camera frame (or None when
no hand is seen) with the frame's time. For each pose there is a short get-ready, then a hold during which frames are recorded
(the hint asks you to turn your hand a little, so the examples cover real use). A pose with too few frames is asked again, twice,
then skipped (the rules cover it).
"""
from __future__ import annotations

import numpy as np

from .handfeat import hand_features

STEPS = [
    {"pose": "palm", "title": "Open palm", "do": "Open your hand flat, fingers spread, palm toward the camera."},
    {"pose": "fist", "title": "Fist", "do": "Close your hand into a fist. Rest your thumb the way you naturally do."},
    {"pose": "thumb_up", "title": "Thumbs-up", "do": "Make a fist and point your thumb straight up."},
    {"pose": "thumb_down", "title": "Thumbs-down", "do": "Make a fist and point your thumb down."},
    {"pose": "click", "title": "Pinch", "do": "Touch the tip of your thumb to the tip of your index finger."},
    {"pose": "point", "title": "One finger", "do": "Only your index finger up; the others curled."},
    {"pose": "scroll", "title": "Two fingers", "do": "Index and middle fingers up; the others curled."},
    {"pose": "right", "title": "Three fingers", "do": "Index, middle and ring fingers up; the little finger curled."},
    {"pose": "ell", "title": "L shape", "do": "Thumb out to the side and index finger up, like an L."},
]
HINT = "Keep holding it, and slowly turn your hand a little left and right."


class Calibrator:
    def __init__(self, steps=STEPS, ready_s: float = 3.0, hold_s: float = 6.0, min_frames: int = 60, retries: int = 2, skip_s: float = 0.7, trim: float = 0.1):
        self.steps, self.ready_s, self.hold_s, self.min_frames, self.max_retries = steps, ready_s, hold_s, min_frames, retries
        self.skip_s, self.trim = skip_s, trim          # ignore the first moments of a hold (you are still getting into the pose) and the odd frames furthest from the rest
        self.i = 0
        self.phase = "ready"                 # "ready" | "hold" | "done"
        self.t_phase = None
        self.retry = 0
        self.frames: list = []
        self.samples: dict = {}
        self.skipped: list = []
        self.message = ""
        self.elapsed = 0.0

    @property
    def done(self) -> bool:
        return self.phase == "done"

    def update(self, feats, t: float) -> None:
        """feats: the 63-number normalised landmarks of the hand (features.normalize), or None if no hand."""
        if self.done:
            return
        if self.t_phase is None:
            self.t_phase = t
        elapsed = self.elapsed = t - self.t_phase
        if self.phase == "ready":
            if elapsed >= self.ready_s:
                self.phase, self.t_phase, self.frames, self.message = "hold", t, [], ""
            return
        if feats is not None and elapsed >= self.skip_s:
            self.frames.append(hand_features(np.asarray(feats, np.float32).reshape(21, 3)))
        if elapsed >= self.hold_s:
            self._finish_step(t)

    def _finish_step(self, t: float) -> None:
        pose = self.steps[self.i]["pose"]
        if len(self.frames) >= self.min_frames:
            self.samples[pose] = self._trimmed(np.vstack(self.frames))
            self._next(t)
        elif self.retry < self.max_retries:
            self.retry += 1
            self.phase, self.t_phase, self.message = "ready", t, "I could not see your hand well enough. Let's try that one again."
        else:
            self.skipped.append(pose)                                   # the rules will handle this pose
            self._next(t)

    def _trimmed(self, X):
        """Drop the frames furthest from the pose's typical look (a late start, a blink of tracking): robust centre and spread."""
        if self.trim <= 0 or len(X) < 20:
            return X
        centre = np.median(X, axis=0)
        spread = np.maximum(np.median(np.abs(X - centre), axis=0) * 1.4826, 0.02)
        d = np.sqrt((((X - centre) / spread) ** 2).sum(axis=1))
        return X[d <= np.quantile(d, 1.0 - self.trim)]

    def _next(self, t: float) -> None:
        self.i += 1
        self.retry = 0
        self.t_phase, self.frames = t, []
        self.phase = "done" if self.i >= len(self.steps) else "ready"

    def snapshot(self) -> dict:
        step = self.steps[min(self.i, len(self.steps) - 1)]
        span = self.ready_s if self.phase == "ready" else self.hold_s
        return {"step": min(self.i, len(self.steps)), "total": len(self.steps), "pose": step["pose"], "title": step["title"], "do": step["do"],
                "hint": HINT, "phase": self.phase, "collected": len(self.frames), "needed": self.min_frames, "message": self.message,
                "seconds": span, "elapsed": round(self.elapsed, 2), "done_poses": list(self.samples), "skipped": list(self.skipped)}
