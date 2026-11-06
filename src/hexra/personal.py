"""A recogniser taught by the user's own hand.

The rules in poses.py are written for an average hand; yours may differ (a fist with the thumb tucked against the index finger looks
like a pinch to them). Calibration records what YOUR poses look like (handfeat.py), and this classifies by the nearest recorded
examples (k nearest neighbours, plain numpy). Anything that is not close to any example falls back to the rules, so an unusual
moment never becomes a confident wrong pose. Before a calibration is accepted it is cross-validated on blocks of its own
recording, which also says which poses your hand makes look alike.
"""
from __future__ import annotations

import json
from collections import Counter, deque
from pathlib import Path

import numpy as np

from .handfeat import hand_features
from .poses import RuleRecognizer

K = 7


class PersonalModel:
    def __init__(self, poses, X, y, mean, std, max_dist):
        self.poses = list(poses)
        self.X, self.y = np.asarray(X, np.float32), np.asarray(y, np.int32)
        self.mean, self.std = np.asarray(mean, np.float32), np.asarray(std, np.float32)
        self.max_dist = float(max_dist)

    # ---- learning
    @classmethod
    def fit(cls, samples: dict, max_dist: float = float("inf")):
        poses = [p for p in samples if len(samples[p])]
        X = np.vstack([np.asarray(samples[p], np.float32) for p in poses])
        y = np.concatenate([np.full(len(samples[p]), i, np.int32) for i, p in enumerate(poses)])
        mean = X.mean(axis=0)
        std = np.maximum(X.std(axis=0), 0.02)                         # a feature that barely varies must not blow up
        return cls(poses, (X - mean) / std, y, mean, std, max_dist)

    # ---- using it
    def predict_vector(self, feat):
        """(pose, distance to the nearest examples of that pose in units of how much your own poses vary)."""
        z = (np.asarray(feat, np.float32) - self.mean) / self.std
        d = np.sqrt(((self.X - z) ** 2).sum(axis=1))
        k = min(K, len(d))
        idx = np.argpartition(d, k - 1)[:k]
        votes = Counter()
        for i in idx:
            votes[int(self.y[i])] += 1.0 / (float(d[i]) + 0.05)
        best = max(votes, key=votes.get)
        dist = float(np.mean([d[i] for i in idx if self.y[i] == best]))
        return self.poses[best], dist

    # ---- files
    def save(self, path) -> None:
        np.savez_compressed(path, poses=np.array(self.poses), X=self.X, y=self.y, mean=self.mean, std=self.std, max_dist=self.max_dist)

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=False)
        return cls([str(p) for p in z["poses"]], z["X"], z["y"], z["mean"], z["std"], float(z["max_dist"]))


def cross_validate(samples: dict, blocks: int = 4) -> dict:
    """Hold out one contiguous block of each pose's recording at a time (so neighbouring frames cannot leak), train on the rest,
    classify the held-out frames. Returns per-pose accuracy, which poses were mixed up, and the typical held-out distance."""
    poses = [p for p in samples if len(samples[p]) >= blocks * 5]
    conf = {p: Counter() for p in poses}
    dists = []
    for b in range(blocks):
        train, test = {}, {}
        for p in poses:
            a = np.asarray(samples[p], np.float32)
            edges = np.linspace(0, len(a), blocks + 1).astype(int)
            lo, hi = edges[b], edges[b + 1]
            test[p] = a[lo:hi]
            train[p] = np.vstack([a[:lo], a[hi:]])
        model = PersonalModel.fit(train)
        for p in poses:
            for f in test[p]:
                got, dist = model.predict_vector(f)
                conf[p][got] += 1
                dists.append(dist)
    acc = {p: conf[p][p] / max(sum(conf[p].values()), 1) for p in poses}
    mixups = []
    for p in poses:
        total = max(sum(conf[p].values()), 1)
        for q, n in conf[p].items():
            if q != p and n / total >= 0.08:
                mixups.append({"pose": p, "looks_like": q, "share": round(n / total, 2)})
    return {"accuracy": acc, "mixups": sorted(mixups, key=lambda m: -m["share"]),
            "typical_distance": float(np.percentile(dists, 95)) if dists else 0.0}


def build(samples: dict):
    """Cross-validate, then fit the final model on all examples. Returns (model, report)."""
    report = cross_validate(samples)
    model = PersonalModel.fit(samples, max_dist=max(report["typical_distance"] * 1.5, 1.0))
    report["poses"] = list(model.poses)
    report["examples"] = {p: int(len(samples[p])) for p in model.poses}
    return model, report


class PersonalRecognizer:
    """Same interface as RuleRecognizer. Falls back to the rules for anything unfamiliar; smooths over the last 3 frames."""

    def __init__(self, model: PersonalModel, fallback: RuleRecognizer | None = None, smooth: int = 3):
        self.model = model
        self.fallback = fallback or RuleRecognizer()
        self._recent = deque(maxlen=max(1, smooth))

    def predict_features(self, feats) -> str:
        rule = self.fallback.predict_features(feats)                  # always run it: it keeps its own hold/stay memory up to date
        pts = np.asarray(feats, np.float32).reshape(21, 3)
        pose, dist = self.model.predict_vector(hand_features(pts))
        got = pose if dist <= self.model.max_dist else rule
        self._recent.append(got)
        return Counter(self._recent).most_common(1)[0][0]

    predict_points = predict_features


def save_report(path, report: dict) -> None:
    Path(path).write_text(json.dumps(report), encoding="utf-8")
