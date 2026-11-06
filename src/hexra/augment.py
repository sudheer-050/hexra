"""Landmark augmentation: simulate other hand sizes, in-plane rotations, small tilts and tracking noise."""
from __future__ import annotations

import numpy as np


def augment(X: np.ndarray, copies: int = 4, seed: int = 0) -> np.ndarray:
    """Return `copies` randomised variants of every row of X (n, 63). Rows are normalised features."""
    rng = np.random.default_rng(seed)
    pts = X.reshape(-1, 21, 3)
    out = []
    for _ in range(copies):
        n = len(pts)
        a = np.deg2rad(rng.uniform(-20, 20, n))            # in-plane rotation
        t = np.deg2rad(rng.uniform(-15, 15, n))            # tilt about the vertical axis
        c, s = np.cos(a), np.sin(a)
        ct, st = np.cos(t), np.sin(t)
        x, y, z = pts[..., 0], pts[..., 1], pts[..., 2]
        x2 = c[:, None] * x - s[:, None] * y
        y2 = s[:, None] * x + c[:, None] * y
        x3 = ct[:, None] * x2 + st[:, None] * z
        z3 = -st[:, None] * x2 + ct[:, None] * z
        p = np.stack([x3, y2, z3], -1)
        p *= rng.uniform(0.9, 1.1, (n, 1, 1))              # per-hand scale
        p[..., :2] *= rng.uniform(0.92, 1.08, (n, 1, 2))   # aspect change (finger lengths differ between people)
        p += rng.normal(0, 0.012, p.shape)                 # landmark jitter
        out.append(p.reshape(n, 63))
    return np.concatenate(out).astype(np.float32)
