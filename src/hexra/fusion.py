"""Two cameras, one hand: fuse what each camera sees into a single, steadier hand.

This is NOT a 3D reconstruction. Each camera gives a flat picture with hand landmarks. What is fused:

* the point that drives the cursor (the average of the four knuckles): both cameras' estimates are averaged once the app has
  learned how the two views line up (a plain affine map camera 2 -> camera 1, learned automatically from moments when both
  cameras see the hand; no set-up step), so independent tracking noise partly cancels;
* the pose and finger shape come from whichever camera has the better view (the other camera's finger shapes are NOT blended,
  because the same finger looks different from a different angle). The choice has hysteresis so the pose does not flicker.

If one camera loses the hand, the other carries on at once. The output never jumps when the source changes: an offset keeps the
cursor point continuous. The mode is reported so nothing happens silently ("fused", "camera 1 only", "learning 40%").
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

KNUCKLES = (5, 9, 13, 17)


@dataclass
class Observation:
    """What one camera saw in one frame."""
    t: float                     # when the camera captured the frame
    lm: list                     # 21 landmarks with .x .y (.z), normalised 0..1 in that camera's own picture
    label: str                   # "Left" / "Right" as the user sees it
    score: float = 1.0           # detector confidence, 0..1


@dataclass
class Fused:
    lm: list                     # landmarks in camera 1's frame, positioned so the knuckle average is the fused point
    raw: list                    # the best camera's own landmarks (for pose recognition: finger shapes are not blended)
    label: str
    point: tuple                 # the fused cursor point (camera 1 frame)
    mode: str                    # "fused" | "camera 1 only" | "camera 2 only" | "learning NN%"
    best: int                    # which camera supplied the pose (0 or 1)


def control_point(lm) -> np.ndarray:
    return np.array([sum(lm[i].x for i in KNUCKLES) / len(KNUCKLES), sum(lm[i].y for i in KNUCKLES) / len(KNUCKLES)])


def quality(o: Observation) -> float:
    """How good this camera's view of the hand is, 0..1: detector confidence x how much of the hand is inside the picture
    x how large the hand appears (a bigger hand is tracked more precisely)."""
    inside = sum(1 for p in o.lm if 0.01 <= p.x <= 0.99 and 0.01 <= p.y <= 0.99) / max(len(o.lm), 1)
    xs, ys = [p.x for p in o.lm], [p.y for p in o.lm]
    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    size = min(1.0, max(0.3, extent / 0.12))
    return max(0.0, min(1.0, o.score)) * inside * size


class AffineMap:
    """Learns p1 ~= M @ [p2, 1] from pairs of the same hand point seen at the same moment by both cameras (ridge least squares)."""

    def __init__(self, maxlen: int = 400, ridge: float = 1e-4):
        self.pairs: deque = deque(maxlen=maxlen)
        self.ridge = ridge
        self.M = None
        self._dirty = False

    def add(self, p1, p2) -> None:
        self.pairs.append((np.asarray(p1, float), np.asarray(p2, float)))
        self._dirty = True

    def clear(self) -> None:
        self.pairs.clear()
        self.M, self._dirty = None, False

    @property
    def spread(self) -> float:
        if len(self.pairs) < 5:
            return 0.0
        a = np.array([p[0] for p in self.pairs])
        return float(min(a[:, 0].std(), a[:, 1].std()))          # how well the hand has covered both directions

    def fit(self) -> None:
        if not self._dirty or len(self.pairs) < 8:
            return
        P1 = np.array([p[0] for p in self.pairs])
        P2 = np.hstack([np.array([p[1] for p in self.pairs]), np.ones((len(self.pairs), 1))])
        A = P2.T @ P2 + self.ridge * np.eye(3)
        self.M = np.linalg.solve(A, P2.T @ P1).T                # 2x3
        self._dirty = False

    def apply(self, p2):
        p = np.asarray(p2, float)
        return self.M[:, :2] @ p + self.M[:, 2]

    def rms(self) -> float:
        if self.M is None or not self.pairs:
            return 1.0
        err = [np.linalg.norm(self.apply(p2) - p1) for p1, p2 in self.pairs]
        return float(np.sqrt(np.mean(np.square(err))))


class Fuser:
    def __init__(self, max_age_s: float = 0.10, max_pair_gap_s: float = 0.045, min_pairs: int = 120, min_spread: float = 0.04,
                 max_rms: float = 0.03, disagree: float = 0.10, switch_margin: float = 0.08, switch_hold_s: float = 0.4):
        self.max_age_s, self.max_pair_gap_s = max_age_s, max_pair_gap_s
        self.min_pairs, self.min_spread, self.max_rms, self.disagree = min_pairs, min_spread, max_rms, disagree
        self.switch_margin, self.switch_hold_s = switch_margin, switch_hold_s
        self.map = AffineMap()
        self._seen_pair = (None, None)
        self.best = 0
        self._challenger_since = None
        self._source = None                  # which source produced the last output: "fused", 0 or 1
        self._offset = np.zeros(2)
        self._last_point = None
        self._strikes = 0

    # ---- learning state
    @property
    def ready(self) -> bool:
        return (self.map.M is not None and len(self.map.pairs) >= self.min_pairs and self.map.spread >= self.min_spread
                and self.map.rms() <= self.max_rms)

    @property
    def progress(self) -> float:
        return min(1.0, len(self.map.pairs) / self.min_pairs, self.map.spread / self.min_spread if self.min_spread else 1.0)

    # ---- one step
    def update(self, obs0, obs1, t: float):
        """Newest observation from camera 1 and camera 2 (None if that camera sees no hand). Returns Fused or None."""
        fresh = [o if (o is not None and t - o.t <= self.max_age_s) else None for o in (obs0, obs1)]    # too old = not seen
        a, b = fresh
        if a is None and b is None:
            return None

        pa = control_point(a.lm) if a else None
        pb = control_point(b.lm) if b else None
        mapped_b = None
        trusted = True

        if a is not None and b is not None and abs(a.t - b.t) <= self.max_pair_gap_s and (a.t, b.t) != self._seen_pair:
            self._seen_pair = (a.t, b.t)
            if self.map.M is not None and self.ready:
                if np.linalg.norm(self.map.apply(pb) - pa) > self.disagree:        # the views stopped agreeing: do not trust the map
                    trusted = False
                    self._strikes += 1
                    if self._strikes >= 12:
                        self.map.clear()
                        self._strikes = 0
                else:
                    self._strikes = 0
                    self.map.add(pa, pb)
            else:
                self.map.add(pa, pb)
            self.map.fit()
        if b is not None and self.map.M is not None and self.ready and trusted:
            mapped_b = self.map.apply(pb)

        # ---- which camera has the better view (for pose): hysteresis so it does not flicker
        if a is not None and b is None:
            self.best, self._challenger_since = 0, None
        elif b is not None and a is None:
            self.best, self._challenger_since = 1, None
        else:
            cur, other = (a, b) if self.best == 0 else (b, a)
            if quality(other) > quality(cur) + self.switch_margin:
                self._challenger_since = self._challenger_since if self._challenger_since is not None else t
                if t - self._challenger_since >= self.switch_hold_s:
                    self.best, self._challenger_since = 1 - self.best, None
            else:
                self._challenger_since = None

        # ---- the cursor point
        if a is not None and b is not None and mapped_b is not None:
            wa, wb = max(quality(a), 0.05) ** 2, max(quality(b), 0.05) ** 2          # the better view counts for more
            point, source, mode = (wa * pa + wb * mapped_b) / (wa + wb), "fused", "fused"
        elif a is not None and b is not None:
            source, point = 0, pa                      # camera 1 is the reference frame until the two views are matched
            mode = f"learning {int(self.progress * 100)}%"
        elif a is not None:
            point, source, mode = pa, 0, "camera 1 only"
        else:
            source = 1
            point = mapped_b if mapped_b is not None else pb
            mode = "camera 2 only"

        # no jump when the source changes: keep the output continuous
        if source != self._source and self._last_point is not None:
            self._offset = self._last_point - point
        elif self._source is None:
            self._offset = np.zeros(2)
        if source == "fused" and self._source == "fused":
            self._offset *= 0.9                      # fused is the reference; let any carried offset fade out smoothly
        point = point + self._offset
        self._source, self._last_point = source, point.copy()

        best_obs = a if (self.best == 0 and a is not None) or b is None else b
        use0 = best_obs is a
        # landmarks in camera 1's frame: shape from the best camera (camera 2's mapped by the affine map when it is ready),
        # shifted so the knuckle average is exactly the fused point
        if use0 or self.map.M is None or not self.ready:
            pts = np.array([[p.x, p.y] for p in best_obs.lm])
        else:
            pts = np.array([self.map.apply([p.x, p.y]) for p in best_obs.lm])
        shift = point - pts[list(KNUCKLES)].mean(axis=0)
        z = [getattr(p, "z", 0.0) for p in best_obs.lm]
        lm = [SimpleNamespace(x=float(pts[i, 0] + shift[0]), y=float(pts[i, 1] + shift[1]), z=z[i]) for i in range(len(pts))]
        return Fused(lm=lm, raw=best_obs.lm, label=best_obs.label, point=(float(point[0]), float(point[1])), mode=mode,
                     best=0 if use0 else 1)
