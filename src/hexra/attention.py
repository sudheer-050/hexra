"""Attention gate: gestures only work while you are FACING THE SCREEN.

Turn your head away to talk to a friend or look at your phone and Hexra pauses by itself; look back and it carries on. It does
not identify you (that is the face lock); it only asks "is a face turned toward the camera?".

* A small face detector (OpenCV's YuNet, 233 KB, runs on the CPU) finds the largest face about five times a second, on a
  background thread, so the cursor is never delayed.
* From its five landmarks (eyes, nose tip, mouth corners) the head turn is estimated: how far the nose tip sits to the side of
  the point between the eyes, compared with the distance between the eyes. For an average head that ratio is about
  0.476 * tan(turn), so 0 degrees is facing the camera and it grows as the head turns.
* Gestures are allowed while a face turned less than `max_turn_deg` was seen in the last `grace_s` seconds. The grace period
  means a quick glance at the keyboard or the phone does not interrupt a drag; looking away for longer does.

It assumes the camera is on or near the screen you are looking at. If your camera sits well to one side, raise max_turn_deg.
"""
from __future__ import annotations

import logging
import math
import threading
from pathlib import Path

log = logging.getLogger("hexra")

DEFAULTS = {
    "enabled": False,
    "model": "models/face_detection_yunet_2023mar.onnx",
    "max_turn_deg": 35.0,      # a head turned further than this counts as looking away
    "grace_s": 1.0,            # ...but only once it has been turned (or gone) for this long
    "check_every_s": 0.2,      # how often a picture is checked
    "require_face": True,      # True: no face in the picture counts as looking away. False: only a clearly turned face does
}
NOSE_PROTRUSION = 0.476        # nose-tip offset / eye distance = this * tan(head turn)  (about 30 mm nose depth, 63 mm between the eyes)


def turn_degrees(face) -> float:
    """Head turn left or right in degrees (0 = facing the camera) from one YuNet face row:
    [x, y, w, h, right-eye x, y, left-eye x, y, nose x, y, mouth corners..., score]."""
    rex, rey, lex, ley, nx, ny = (float(face[i]) for i in (4, 5, 6, 7, 8, 9))
    eye = math.hypot(lex - rex, ley - rey)
    if eye < 1e-6:
        return 90.0
    ux, uy = (lex - rex) / eye, (ley - rey) / eye                 # along the line through the eyes (a tilted head is fine)
    off = (nx - (rex + lex) / 2) * ux + (ny - (rey + ley) / 2) * uy
    return math.degrees(math.atan(abs(off) / eye / NOSE_PROTRUSION))


def largest_face(faces):
    """The biggest face in the picture: you are closest to the screen, anyone standing behind you is smaller."""
    if faces is None or len(faces) == 0:
        return None
    return max(faces, key=lambda f: float(f[2]) * float(f[3]))


class AttentionGate:
    """The decision, with no camera and no threads, so it is fully testable."""

    def __init__(self, max_turn_deg: float = 35.0, grace_s: float = 1.0, require_face: bool = True):
        self.max_turn_deg, self.grace_s, self.require_face = float(max_turn_deg), float(grace_s), bool(require_face)
        self.turn = None          # the last measured head turn in degrees; None = no face in the last picture
        self._last_ok = None      # when someone facing the screen was last seen

    def update(self, turn_deg, t: float) -> None:
        self.turn = turn_deg
        ok = (not self.require_face) if turn_deg is None else turn_deg <= self.max_turn_deg
        if ok:
            self._last_ok = t

    def allowed(self, t: float) -> bool:
        return self._last_ok is not None and t - self._last_ok <= self.grace_s


class YuNetDetector:
    def __init__(self, model_path):
        import cv2

        self._cv2 = cv2
        self._det = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), 0.7, 0.3, 5000)
        self._size = (320, 320)

    def detect(self, frame):
        h, w = frame.shape[:2]
        if (w, h) != self._size:
            self._det.setInputSize((w, h))
            self._size = (w, h)
        _, faces = self._det.detect(frame)
        return faces


class Attention:
    def __init__(self, detector, gate: AttentionGate, check_every_s: float = 0.2, threaded: bool = True):
        self.detector, self.gate, self.check_every_s = detector, gate, check_every_s
        self.faces = 0
        self._last_check = -1e9
        self._threaded = threaded
        self._cond = threading.Condition()
        self._pending = None
        self._stop = False
        if threaded:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    # ---- called by the control loop (never blocks) ----
    def submit(self, frame, t: float) -> None:
        if t - self._last_check < self.check_every_s:
            return
        self._last_check = t
        if not self._threaded:
            self._analyze(frame, t)
            return
        with self._cond:
            if self._pending is None:                 # the worker is idle; otherwise skip this picture
                self._pending = (frame.copy(), t)
                self._cond.notify()

    def allowed(self, t: float) -> bool:
        return self.gate.allowed(t)

    def describe(self, t: float) -> str:
        g = self.gate
        if g.turn is None:
            if g._last_ok is None or g.allowed(t):
                return "looking for a face..."
            return "no face seen: gestures paused"
        if g.turn <= g.max_turn_deg:
            return f"facing the screen (turn {g.turn:.0f} deg)"
        return f"LOOKING AWAY (turn {g.turn:.0f} deg): gestures paused" if not g.allowed(t) else f"looking away ({g.turn:.0f} deg)..."

    # ---- worker ----
    def _analyze(self, frame, t: float) -> None:
        try:
            faces = self.detector.detect(frame)
        except Exception as exc:                      # a detector hiccup must never stop the app
            log.warning("Attention check failed (%s)", exc)
            return
        face = largest_face(faces)
        self.faces = 0 if faces is None else len(faces)
        self.gate.update(None if face is None else turn_degrees(face), t)

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._pending is not None or self._stop)
                if self._stop:
                    return
                frame, t = self._pending
                self._pending = None
            self._analyze(frame, t)

    def close(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()


def build(options: dict):
    """An Attention for the given options, or None when it is off or the face model is missing."""
    opts = {**DEFAULTS, **(options or {})}
    if not opts["enabled"]:
        return None
    model = Path(opts["model"])
    if not model.exists():
        log.warning("Attention gate is on but %s is missing, so it is off. (It is the face detector, 233 KB.)", model)
        return None
    gate = AttentionGate(opts["max_turn_deg"], opts["grace_s"], opts["require_face"])
    return Attention(YuNetDetector(model), gate, check_every_s=float(opts["check_every_s"]))
