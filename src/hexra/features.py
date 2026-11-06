"""Turn 21 MediaPipe landmarks into a position/scale/handedness-invariant feature vector."""
from __future__ import annotations

import numpy as np

N_FEATURES = 63  # 21 landmarks x (x, y, z)


def normalize(landmarks, hand_label: str) -> np.ndarray:
    """Wrist-relative, scale-normalised, left hands mirrored to look like right hands.

    `landmarks` is a sequence of 21 objects with .x .y .z. `hand_label` is
    "Left"/"Right" as the user sees their own hand (frame already mirrored).
    """
    pts = np.array([[p.x, p.y, p.z] for p in landmarks], dtype=np.float32)
    if pts.shape != (21, 3):
        raise ValueError(f"expected 21 landmarks, got {pts.shape[0]}")
    pts -= pts[0]  # wrist at origin
    scale = np.linalg.norm(pts[:, :2], axis=1).max()
    if scale < 1e-6:
        raise ValueError("degenerate hand (zero size)")
    pts /= scale
    if hand_label.lower() == "left":
        pts[:, 0] *= -1
    return pts.reshape(-1)
