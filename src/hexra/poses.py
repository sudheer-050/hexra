"""Pose recognisers: classify a normalised hand (21x3 points) into one of six poses.

RuleRecognizer: hand-written geometry. Works with zero training and is the baseline to beat.
MLRecognizer:   a classifier trained on your own recordings (python -m hexra.train).
"""
from __future__ import annotations

import numpy as np

POSES = ["palm", "fist", "point", "click", "right", "scroll"]
POSE_HELP = {
    "palm": "open hand, all fingers spread (moves the cursor)",
    "fist": "closed fist: grab the front window and move it with your hand",
    "point": "only the index finger up (neutral: cursor stops)",
    "click": "pinch thumb + index finger together (left click / drag)",
    "right": "three fingers up: index + middle + ring, pinky down (right click)",
    "scroll": "two fingers up: index + middle, others closed; move your hand up/down/left/right to scroll",
}
# Window-command poses. They are recognised by RuleRecognizer only (not part of the trainable six) and each is a
# one-shot command (see controller.py), so no pose is shared between a command and a movement.
COMMAND_POSES = ["thumb_up", "thumb_down", "ell"]
COMMAND_HELP = {
    "thumb_up": "thumbs-up (fist with the thumb straight up): maximise / restore the window under the cursor",
    "thumb_down": "thumbs-down (fist with the thumb straight down): minimise the window under the cursor",
    "ell": "L shape (thumb out sideways, index finger up, the rest closed), held: close the window under the cursor",
}
WRIST, THUMB_TIP, INDEX_TIP, MIDDLE_TIP = 0, 4, 8, 12
_FINGERS = {"index": (6, 8), "middle": (10, 12), "ring": (14, 16), "pinky": (18, 20)}  # (pip, tip)
_CHAINS = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20)}  # knuckle..tip


def _straightness(p, ids) -> float:
    """How straight a finger is as seen by the camera: knuckle-to-tip distance / the length of the bones along the way.
    1.0 = perfectly straight. A straight finger projects to a straight line from ANY viewing angle, so unlike distance
    from the wrist this does not shrink when you turn your hand."""
    m, a, b, t = (p[i, :2] for i in ids)
    path = np.linalg.norm(a - m) + np.linalg.norm(b - a) + np.linalg.norm(t - b)
    return float(np.linalg.norm(t - m) / max(path, 1e-9))


def _d(p, a, b) -> float:
    return float(np.linalg.norm(p[a, :2] - p[b, :2]))


class RuleRecognizer:
    """Hand-written pose rules.

    A finger is EXTENDED when it is STRAIGHT (see _straightness), which stays true however you turn your hand, so an
    open palm is never mistaken for three fingers (right click) when rotated. A finger is CURLED when it is clearly bent,
    or clearly short-reaching (fingertip-to-wrist distance / palm length, "reach"). In between it is unsure and the
    hand counts as an open palm (which only moves the cursor), never as a click-type gesture.
    A fist STICKS: once you are in a fist it stays one until a finger clearly opens, so tilting or moving the hand
    (and a thumb resting against the index finger) cannot drop a window you are dragging.
    """

    # A fist must be a DELIBERATE, nearly closed fist: index, middle and ring must each be clearly folded (low straightness)
    # AND short-reaching. Reach alone is misleading (a hand tilted forward shortens open fingers), straightness alone
    # misses fists seen from the side, so both are required. Once in a fist it stays one until a finger clearly opens.
    FIST_REACH_ENTER, FIST_STRAIGHT_ENTER = 1.10, 0.60
    FIST_REACH_STAY, FIST_STRAIGHT_STAY = 1.70, 0.93
    STRAIGHT = 0.88       # straightness at or above this = extended finger
    STRAIGHT_STAY = 0.78  # ...but a finger that was extended a moment ago stays "extended" down to this (no flicker)
    BENT = 0.80           # straightness below this = curled finger
    SHORT_REACH = 1.10    # ...or a not-quite-straight finger that reaches less than this
    # Thumb: "out" when its bones form a straight line AND it reaches well away from the palm. A thumb resting on a fist
    # is short and bent, so an ordinary fist is never read as thumbs-up.
    THUMB_STRAIGHT, THUMB_LENGTH = 0.85, 0.50
    THUMB_VERTICAL = 0.60      # |sideways| <= this x |vertical| counts as pointing up/down (about 30 degrees)
    THUMB_VERTICAL_STAY = 0.85  # ...a little looser once the pose is already held, so it does not flicker
    ELL_ANGLE = (75.0, 125.0)  # the angle between thumb and index finger for an "L": clearly sideways, not just a thumb held out
    THUMB_BONE_MIN = 0.04      # a thumb whose joints coincide has no usable direction (tracking dropout): ignored

    def __init__(self, pinch_ratio: float = 0.25, release_ratio: float = 0.40):
        self.pinch_ratio = pinch_ratio      # fingers must come this close to START a pinch
        self.release_ratio = release_ratio  # ...but may drift this far apart (hand tilting) before it ends
        self._pinched = False
        self._last = None
        self._ext_prev: dict = {}

    def predict_points(self, pts: np.ndarray) -> str:
        size = _d(pts, WRIST, 9) or 1e-6  # wrist to middle-finger knuckle
        reach = {n: _d(pts, WRIST, tip) / size for n, (_, tip) in _FINGERS.items()}
        straight = {n: _straightness(pts, ids) for n, ids in _CHAINS.items()}
        limit = self.release_ratio if self._pinched else self.pinch_ratio
        self._pinched = _d(pts, THUMB_TIP, INDEX_TIP) / size < limit
        stay = self._last == "fist"
        r_lim, s_lim = (self.FIST_REACH_STAY, self.FIST_STRAIGHT_STAY) if stay else (self.FIST_REACH_ENTER, self.FIST_STRAIGHT_ENTER)
        fist_like = all(reach[n] < r_lim and straight[n] < s_lim for n in ("index", "middle", "ring"))
        ext = {n: s >= (self.STRAIGHT_STAY if self._ext_prev.get(n) else self.STRAIGHT) for n, s in straight.items()}
        cur = {n: s < self.BENT or (s < self.STRAIGHT and reach[n] < self.SHORT_REACH) for n, s in straight.items()}
        pose = self._thumb_pose(pts, size, straight, reach, ext, cur)
        if pose is not None:
            pass                              # a window-command pose (thumbs up / down, L)
        elif self._last == "fist" and fist_like:
            pose = "fist"                    # sticky: a thumb against the index finger does not turn a fist into a click
        elif self._pinched:
            pose = "click"
        elif fist_like:
            pose = "fist"
        else:
            if all(ext.values()):
                pose = "palm"
            elif ext["index"] and cur["middle"] and cur["ring"] and cur["pinky"]:
                pose = "point"
            elif ext["index"] and ext["middle"] and cur["ring"] and cur["pinky"]:
                pose = "scroll"
            elif ext["index"] and ext["middle"] and ext["ring"] and cur["pinky"]:
                pose = "right"
            else:
                pose = "palm"                # anything ambiguous is neutral (it only moves the cursor)
        self._last = pose
        self._ext_prev = ext if pose in ("palm", "point", "scroll", "right") else {}
        return pose

    def _thumb_pose(self, pts, size, straight, reach, ext, cur):
        """thumb_up / thumb_down / ell, or None. Never starts while a fist is held: a thumb sticking out of a fist that is
        dragging a window must not become a command."""
        if self._last == "fist":
            return None
        if min(_d(pts, a, b) for a, b in ((1, 2), (2, 3), (3, 4))) / size < self.THUMB_BONE_MIN:
            return None
        thumb_straight = _straightness(pts, (1, 2, 3, 4))
        vec = pts[4, :2] - pts[2, :2]
        if thumb_straight < self.THUMB_STRAIGHT or float(np.linalg.norm(vec)) / size < self.THUMB_LENGTH:
            return None
        held = self._last in ("thumb_up", "thumb_down")
        r_lim, s_lim = (self.FIST_REACH_STAY, self.FIST_STRAIGHT_STAY) if held else (self.FIST_REACH_ENTER, self.FIST_STRAIGHT_ENTER)
        four_curled = all(reach[n] < r_lim and straight[n] < s_lim for n in ("index", "middle", "ring")) and cur["pinky"]
        tilt = self.THUMB_VERTICAL_STAY if held else self.THUMB_VERTICAL
        if four_curled and abs(vec[0]) <= tilt * abs(vec[1]):
            return "thumb_up" if vec[1] < 0 else "thumb_down"       # image y grows downwards
        if ext["index"] and cur["middle"] and cur["ring"] and cur["pinky"]:
            idx = pts[8, :2] - pts[5, :2]
            denom = float(np.linalg.norm(vec) * np.linalg.norm(idx))
            if denom > 1e-9:
                angle = float(np.degrees(np.arccos(np.clip(np.dot(vec, idx) / denom, -1.0, 1.0))))
                if self.ELL_ANGLE[0] <= angle <= self.ELL_ANGLE[1]:
                    return "ell"
        return None

    def predict_features(self, feats) -> str:
        return self.predict_points(np.asarray(feats, dtype=np.float32).reshape(21, 3))


class MLRecognizer:
    def __init__(self, classifier, min_conf: float = 0.6):
        self.clf, self.min_conf = classifier, min_conf

    @classmethod
    def load(cls, path: str, min_conf: float = 0.6) -> "MLRecognizer":
        import joblib

        return cls(joblib.load(path), min_conf)

    def predict_features(self, feats) -> str:
        x = np.asarray(feats, dtype=np.float32).reshape(1, -1)
        if hasattr(self.clf, "predict_proba"):
            proba = self.clf.predict_proba(x)[0]
            i = int(proba.argmax())
            return str(self.clf.classes_[i]) if proba[i] >= self.min_conf else "palm"  # unsure -> neutral (never a grab)
        return str(self.clf.predict(x)[0])
