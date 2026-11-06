"""A short, size- and turn-tolerant description of a hand, used by the personal calibration.

Everything is a ratio (to the palm length: wrist to middle knuckle), so it does not depend on how far you sit from the camera,
and most entries are about shape (how straight, how far out) rather than where the hand points, so a hand turned a little still
looks similar. The thumb gets the most entries because the thumb is what separates a fist, a thumbs-up and a pinch.
"""
from __future__ import annotations

import numpy as np

from .poses import _CHAINS, _FINGERS, _d, _straightness

NAMES = ["straight_index", "straight_middle", "straight_ring", "straight_pinky",
         "reach_index", "reach_middle", "reach_ring", "reach_pinky",
         "thumb_straight", "thumb_len", "thumb_len3d", "thumb_along", "thumb_side_vs_up",
         "thumb_to_index_knuckle", "thumb_to_middle_knuckle3d", "thumb_to_index_tip",
         "spread_index_middle", "spread_middle_ring", "thumb_straight3d"]


def _d3(p, a, b) -> float:
    return float(np.linalg.norm(p[a] - p[b]))


def hand_features(pts) -> np.ndarray:
    """pts: 21 x 3 landmarks (any origin and scale). Returns len(NAMES) floats."""
    p = np.asarray(pts, dtype=np.float32).reshape(21, 3)
    p = p - p[0]                                                    # wrist at the origin
    size = _d(p, 0, 9) or 1e-6
    size3 = _d3(p, 0, 9) or 1e-6
    straight = [_straightness(p, _CHAINS[n]) for n in ("index", "middle", "ring", "pinky")]
    reach = [_d(p, 0, tip) / size for _, (_, tip) in _FINGERS.items()]
    vec = p[4, :2] - p[2, :2]
    axis = p[9, :2] / (float(np.linalg.norm(p[9, :2])) or 1.0)
    along = float(np.dot(p[4, :2], axis)) / size
    side_vs_up = float(np.clip(vec[0] / (abs(vec[1]) + 1e-3), -4.0, 4.0))
    path2 = _d(p, 1, 2) + _d(p, 2, 3) + _d(p, 3, 4)
    path3 = _d3(p, 1, 2) + _d3(p, 2, 3) + _d3(p, 3, 4)
    out = straight + reach + [
        _d(p, 1, 4) / max(path2, 1e-9),                              # thumb_straight
        _d(p, 2, 4) / size,                                          # thumb_len
        _d3(p, 2, 4) / size3,                                        # thumb_len3d (a turned thumb is longer in 3D than on screen)
        along,                                                       # how far the tip is out along the hand's own axis
        side_vs_up,
        _d(p, 4, 5) / size,                                          # tip to the index knuckle
        _d3(p, 4, 9) / size3,                                        # tip to the middle knuckle, in 3D
        _d(p, 4, 8) / size,                                          # tip to the index tip (a pinch is small)
        _d(p, 8, 12) / size, _d(p, 12, 16) / size,                   # how far apart the fingertips are
        _d3(p, 1, 4) / max(path3, 1e-9)]
    return np.asarray(out, dtype=np.float32)
