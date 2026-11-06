"""Multi-camera stereo 3D: camera models, N-view triangulation, rig calibration, saved calibration, 3D volume.

World frame = the reference camera's frame (the first calibrated camera). Units = centimetres (the checkerboard
square size you give during calibration sets the scale).

For each camera i:  X_cam_i = R_i @ X_world + t_i     (the reference camera has R = I, t = 0)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from types import SimpleNamespace

import cv2
import numpy as np

PALM_IDS = (0, 5, 9, 13, 17)   # wrist + the four finger knuckles: a stable "hand centre"


@dataclass
class CameraModel:
    index: int
    size: tuple                 # (width, height) in pixels the calibration was made at
    K: np.ndarray               # 3x3 intrinsics
    dist: np.ndarray            # distortion coefficients
    R: np.ndarray = field(default_factory=lambda: np.eye(3))
    t: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def P(self) -> np.ndarray:
        """3x4 projection matrix for NORMALISED (undistorted) image coordinates."""
        return np.hstack([self.R, self.t.reshape(3, 1)])

    def to_normalized(self, pts_px: np.ndarray) -> np.ndarray:
        """Pixels (N,2) to undistorted normalised camera coordinates (N,2)."""
        p = np.asarray(pts_px, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.undistortPoints(p, self.K, self.dist).reshape(-1, 2)

    def project(self, X: np.ndarray) -> np.ndarray:
        """World points (N,3) to pixels (N,2)."""
        rvec, _ = cv2.Rodrigues(self.R)
        px, _ = cv2.projectPoints(np.asarray(X, np.float64).reshape(-1, 1, 3), rvec, self.t.reshape(3, 1), self.K, self.dist)
        return px.reshape(-1, 2)

    def depth_of(self, X: np.ndarray) -> np.ndarray:
        return (np.asarray(X) @ self.R.T + self.t)[:, 2]


# ----------------------------------------------------------------------------------------------- triangulation
def triangulate_nview(norm_pts: np.ndarray, projections: list, weights=None) -> np.ndarray:
    """Least-squares (DLT) 3D point from V >= 2 views. norm_pts: (V,2) normalised coords, projections: V x (3x4)."""
    rows = []
    for k, (x, y) in enumerate(norm_pts):
        P = projections[k]
        w = 1.0 if weights is None else weights[k]
        rows.append(w * (x * P[2] - P[0]))
        rows.append(w * (y * P[2] - P[1]))
    _, _, vt = np.linalg.svd(np.asarray(rows))
    X = vt[-1]
    return X[:3] / X[3]


@dataclass
class Hand3D:
    points: np.ndarray          # (21,3) in cm, reference-camera frame
    landmarks: list             # 21 objects with .x .y .z, in the reference image, mirrored (see fuse_hand)
    n_views: int
    reproj_px: float
    used: tuple                 # camera indices that contributed

    def center(self) -> np.ndarray:
        return self.points[list(PALM_IDS)].mean(axis=0)


def fuse_hand(observations: dict, models: dict, ref: int, mirror: bool = True, max_reproj_px: float = 20.0):
    """Triangulate a hand seen by several cameras.

    observations: {camera_index: sequence of 21 landmarks with .x .y in 0..1 (image fractions, NOT mirrored)}
    Returns Hand3D, or None when fewer than 2 views agree. The returned `landmarks` are the 3D hand projected back
    into the reference camera (x mirrored when `mirror`, like the single-camera pipeline) so the rest of the app
    can use them exactly like normal landmarks, but they are built from all cameras.
    """
    views = {i: o for i, o in observations.items() if i in models}
    if len(views) < 2:
        return None

    def solve(idxs):
        pts = np.zeros((21, 3))
        norm = {i: models[i].to_normalized(np.array([[p.x * models[i].size[0], p.y * models[i].size[1]] for p in views[i]]))
                for i in idxs}
        Ps = [models[i].P() for i in idxs]
        for k in range(21):
            pts[k] = triangulate_nview(np.array([norm[i][k] for i in idxs]), Ps)
        err = {}
        for i in idxs:
            proj = models[i].project(pts)
            obs = np.array([[p.x * models[i].size[0], p.y * models[i].size[1]] for p in views[i]])
            err[i] = float(np.mean(np.linalg.norm(proj - obs, axis=1)))
        return pts, err

    idxs = sorted(views)
    pts, err = solve(idxs)
    while len(idxs) > 2 and max(err.values()) > max_reproj_px:   # drop the view that disagrees most
        idxs.remove(max(err, key=err.get))
        pts, err = solve(idxs)
    if max(err.values()) > max_reproj_px or any((models[i].depth_of(pts) <= 0).any() for i in idxs):
        return None

    m = models[ref] if ref in models else models[idxs[0]]
    uv = m.project(pts)
    w, h = m.size
    zw = max(float(m.depth_of(pts[:1])[0]), 1e-6)
    scale = (m.K[0, 0] / w) / zw                       # normalised-image units per cm at the wrist depth
    lms = []
    for (u, v), p in zip(uv, pts):
        x = u / w
        lms.append(SimpleNamespace(x=(1.0 - x) if mirror else x, y=v / h, z=(float(m.depth_of(p[None])[0]) - zw) * scale))
    return Hand3D(pts, lms, len(idxs), float(np.mean(list(err.values()))), tuple(idxs))


# ----------------------------------------------------------------------------------------------- calibration
def board_points(cols: int, rows: int, square_cm: float) -> np.ndarray:
    obj = np.zeros((rows * cols, 3), np.float32)
    obj[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_cm
    return obj


def find_board(gray, cols: int, rows: int):
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    ok, corners = cv2.findChessboardCorners(gray, (cols, rows), flags)
    if not ok:
        return None
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), crit).reshape(-1, 2)


def calibrate_intrinsics(obj, img_list, size):
    rms, K, dist, _, _ = cv2.calibrateCamera([obj] * len(img_list), [p.reshape(-1, 1, 2).astype(np.float32) for p in img_list],
                                             size, None, None)
    return float(rms), K, dist


def calibrate_rig(views: list, obj: np.ndarray, sizes: dict, ref: int, min_views: int = 8) -> dict:
    """views: list of {camera_index: (N,2) board corners} (a camera missing from a dict did not see the board).
    Returns {camera_index: CameraModel} with `ref` as the world frame and, in `.rms`, nothing extra (see print)."""
    models, report = {}, {}
    for i, size in sizes.items():
        imgs = [v[i] for v in views if i in v]
        if len(imgs) < min_views:
            raise ValueError(f"camera {i} saw the board in only {len(imgs)} views (need {min_views}+)")
        rms, K, dist = calibrate_intrinsics(obj, imgs, size)
        models[i] = CameraModel(i, tuple(size), K, dist)
        report[i] = rms
    for i in sizes:
        if i == ref:
            continue
        shared = [v for v in views if ref in v and i in v]
        if len(shared) < min_views:
            raise ValueError(f"cameras {ref} and {i} saw the board together only {len(shared)} times (need {min_views}+)")
        ret = cv2.stereoCalibrate([obj] * len(shared), [v[ref].reshape(-1, 1, 2).astype(np.float32) for v in shared],
                                  [v[i].reshape(-1, 1, 2).astype(np.float32) for v in shared],
                                  models[ref].K, models[ref].dist, models[i].K, models[i].dist, tuple(sizes[ref]),
                                  flags=cv2.CALIB_FIX_INTRINSIC)
        rms, R, T = float(ret[0]), ret[5], ret[6]
        models[i].R, models[i].t = np.asarray(R, np.float64), np.asarray(T, np.float64).reshape(3)
        report[i] = (report[i], rms)
    calibrate_rig.last_report = report
    return models


def rebase(models: dict, new_ref: int) -> dict:
    """Re-express every camera relative to a different reference camera (used when the original one is unplugged)."""
    base = models[new_ref]
    out = {}
    for i, m in models.items():
        R = m.R @ base.R.T
        t = m.t - R @ base.t
        out[i] = CameraModel(m.index, m.size, m.K, m.dist, R, t)
    return out


# ----------------------------------------------------------------------------------------------- volume
def volume_from_points(points: np.ndarray, margin_cm: float = 8.0, lo: float = 5.0, hi: float = 95.0) -> dict:
    """Box (cm) around where your hand really was, ignoring the extreme 5% on each side."""
    pts = np.asarray(points, float)
    return {"min": (np.percentile(pts, lo, axis=0) - margin_cm).tolist(),
            "max": (np.percentile(pts, hi, axis=0) + margin_cm).tolist()}


def volume_contains(volume: dict, p: np.ndarray, extra_cm: float = 0.0) -> bool:
    lo, hi = np.asarray(volume["min"]) - extra_cm, np.asarray(volume["max"]) + extra_cm
    return bool(np.all(p >= lo) and np.all(p <= hi))


def rebase_volume(volume: dict, old_models: dict, new_ref: int) -> dict:
    """Axis-aligned box in the NEW reference camera's frame around the old box's 8 corners.

    `old_models` are the models before rebasing (poses relative to the old reference camera), so the new
    reference camera's own R, t convert old-frame points into its frame.
    """
    lo, hi = np.asarray(volume["min"]), np.asarray(volume["max"])
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    m = old_models[new_ref]
    moved = corners @ m.R.T + m.t
    return {"min": moved.min(axis=0).tolist(), "max": moved.max(axis=0).tolist()}


# ----------------------------------------------------------------------------------------------- saving
def save_calibration(path: str, models: dict, ref: int, board: dict, volume=None) -> None:
    data = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reference": ref,
        "board": board,
        "volume": volume,
        "cameras": [{"index": m.index, "size": list(m.size), "K": m.K.tolist(), "dist": np.asarray(m.dist).ravel().tolist(),
                     "R": m.R.tolist(), "t": np.asarray(m.t).ravel().tolist()} for m in models.values()],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


def load_calibration(path: str):
    """Returns (models, reference_index, volume_or_None, board)."""
    with open(path, encoding="utf-8-sig") as fh:
        d = json.load(fh)
    models = {c["index"]: CameraModel(c["index"], tuple(c["size"]), np.array(c["K"]), np.array(c["dist"]),
                                      np.array(c["R"]), np.array(c["t"])) for c in d["cameras"]}
    return models, int(d["reference"]), d.get("volume"), d.get("board", {})


# ----------------------------------------------------------------------------------------------- detection helper
def detect_views(trackers: dict, frames: dict, t: float):
    """Run each camera's tracker on its own UNFLIPPED frame (stereo geometry must not be mirrored).

    Returns ({camera_index: landmarks}, label). Only views whose left/right label matches the majority are kept,
    so two different hands are never triangulated together.
    """
    raw = {}
    for i, frame in frames.items():
        det = trackers[i].detect(frame, int(t * 1000))
        if det:
            raw[i] = det
    if not raw:
        return {}, None
    labels = [d[1] for d in raw.values()]
    label = max(set(labels), key=labels.count)
    return {i: d[0] for i, d in raw.items() if d[1] == label}, label


def mirror_landmarks(landmarks) -> list:
    """Same landmarks as seen in a mirrored (selfie) picture."""
    return [SimpleNamespace(x=1.0 - p.x, y=p.y, z=p.z) for p in landmarks]
