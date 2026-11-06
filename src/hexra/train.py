"""Train the pose classifier on your recordings and compare it with the rule-based baseline.

Test split: the LAST 30% of each pose's recording (contiguous), or whole unseen sessions when there
are 2+ sessions. Both are fairer than a random split of neighbouring frames.
"""
from __future__ import annotations

import csv
import glob
import sys

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, classification_report
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .augment import augment
from .poses import POSES, RuleRecognizer


def load(pattern="data/*.csv"):
    X, y, sess = [], [], []
    for path in glob.glob(pattern):
        with open(path, newline="") as fh:
            rows = csv.reader(fh)
            next(rows)
            for r in rows:
                y.append(r[0]); sess.append(r[1]); X.append([float(v) for v in r[2:]])
    if not X:
        raise SystemExit("No data. Run: python -m hexra.calibrate")
    return np.array(X, np.float32), np.array(y), np.array(sess)


def split_mask(y, sess):
    """True = test sample."""
    uniq = sorted(set(sess))
    if len(uniq) >= 2:
        test_sessions = set(uniq[-1:])
        print(f"Testing on the most recent session ({uniq[-1]}), never seen in training.")
        return np.array([s in test_sessions for s in sess])
    print("One session only: testing on the last 30% of each pose's recording. Record a 2nd session for a firmer test.")
    test = np.zeros(len(y), bool)
    for pose in set(y):
        idx = np.flatnonzero(y == pose)
        test[idx[int(len(idx) * 0.7):]] = True
    return test


def models():
    return {
        "knn": make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=5)),
        "mlp": make_pipeline(StandardScaler(), MLPClassifier((64, 32), max_iter=600, random_state=0)),
    }


def fit_aug(model, X, y, copies=4):
    return model.fit(np.concatenate([X, augment(X, copies)]), np.concatenate([y, np.tile(y, copies)]))


def main():
    X, y, sess = load()
    counts = {p: int((y == p).sum()) for p in POSES}
    print("samples per pose:", counts)
    missing = [p for p, n in counts.items() if n < 20]
    if missing:
        print("WARNING: too few samples for", missing, "- calibrate them first.")
    te = split_mask(y, sess)
    Xtr, Xte, ytr, yte = X[~te], X[te], y[~te], y[te]
    print(f"{len(Xtr)} train / {len(Xte)} test\n")

    rule = RuleRecognizer()
    pred_rule = np.array([rule.predict_features(f) for f in Xte])
    print(f"== rule-based baseline: accuracy {accuracy_score(yte, pred_rule):.3f}")
    results = {}
    for name, m in models().items():
        fit_aug(m, Xtr, ytr)
        pred = m.predict(Xte)
        results[name] = accuracy_score(yte, pred)
        print(f"== {name}: accuracy {results[name]:.3f}")
        if "-v" in sys.argv:
            print(classification_report(yte, pred, zero_division=0))
    if "-v" in sys.argv:
        print("rule-based detail:\n", classification_report(yte, pred_rule, zero_division=0))

    best = max(results, key=results.get)
    final = models()[best]
    fit_aug(final, X, y)
    joblib.dump(final, "models/pose_classifier.joblib")
    print(f"\nSaved '{best}' to models/pose_classifier.joblib (use -v for per-pose detail)")


if __name__ == "__main__":
    main()
