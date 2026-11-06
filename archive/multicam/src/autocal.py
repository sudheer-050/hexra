"""Automatic stereo set-up from YOUR HAND: no checkerboard, no printing.

While you wave a hand in view of 2+ cameras, the matching finger points seen by each camera give the relative camera
poses (essential matrix). A human hand's bones keep the same length, which lets us pick the camera focal length (the
one that makes bone lengths most constant in 3D) and the real-world scale (your palm length, default 9.5 cm).

Less accurate than the checkerboard route (python -m hexra.stereo_calibrate), but fully automatic.
Only landmark numbers are used; no images are stored.

    python -m hexra.autocal                 # run it by hand (also happens automatically on first start)
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from .calibrate import draw_hand
from .cameras import MultiCamera, scan_cameras
from .stereo import (PALM_IDS, CameraModel, detect_views, save_calibration, triangulate_nview,
                     volume_from_points)
from .tracker import HandTracker, ensure_model

BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (0, 9), (9, 10), (10, 11), (11, 12),
         (0, 13), (13, 14), (14, 15), (15, 16), (0, 17), (17, 18), (18, 19), (19, 20), (5, 9), (9, 13), (13, 17)]
FOCAL_GRID = (0.55, 0.65, 0.75, 0.85, 0.95, 1.05)      # focal length as a multiple of the image width
MIN_PAIR_FRAMES = 40
REJECT_CV = 0.20      # bone lengths vary by more than this in 3D: the result is not trustworthy
WARN_CV = 0.12


def K_for(scale: float, size) -> np.ndarray:
    f = scale * size[0]
    return np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1.0]])


def landmarks_to_px(landmarks, size) -> np.ndarray:
    return np.array([[p.x * size[0], p.y * size[1]] for p in landmarks], dtype=np.float64)


def triangulate_frames(obs: dict, models: dict) -> np.ndarray:
    """obs: {cam: (F,21,2) px}, all with the same F. Returns (F,21,3) via batched DLT over the given cameras."""
    cams = list(obs)
    n_frames = obs[cams[0]].shape[0]
    rows = []
    for c in cams:
        norm = models[c].to_normalized(obs[c].reshape(-1, 2))            # (F*21, 2)
        P = models[c].P()
        rows.append(norm[:, 0:1] * P[2] - P[0])
        rows.append(norm[:, 1:2] * P[2] - P[1])
    A = np.stack(rows, axis=1)                                            # (F*21, 2V, 4)
    _, _, vt = np.linalg.svd(A)
    X = vt[:, -1, :]
    return (X[:, :3] / X[:, 3:4]).reshape(n_frames, 21, 3)


def bone_cv(points: np.ndarray) -> float:
    """Mean over bones of (std / mean) of that bone's 3D length across frames. 0 = perfectly constant."""
    a = np.array([b[0] for b in BONES])
    b = np.array([b[1] for b in BONES])
    lengths = np.linalg.norm(points[:, b] - points[:, a], axis=2)         # (F, B)
    return float(np.mean(lengths.std(axis=0) / np.maximum(lengths.mean(axis=0), 1e-9)))


def solve_pair(obs_ref, obs_i, size_ref, size_i, palm_cm: float, fixed_ref_scale=None):
    """Relative pose of camera i w.r.t. the reference from matching hand points.

    obs_*: (F,21,2) pixels. Searches the focal length (shared by both cameras unless `fixed_ref_scale` is given,
    then only camera i's is searched). Returns dict(R, t_cm, scale_ref, scale_i, cv, inliers) or None.
    """
    def evaluate(s_ref, s_i):
        m0 = CameraModel(0, tuple(size_ref), K_for(s_ref, size_ref), np.zeros(5))
        mi = CameraModel(1, tuple(size_i), K_for(s_i, size_i), np.zeros(5))
        n0 = m0.to_normalized(obs_ref.reshape(-1, 2))
        ni = mi.to_normalized(obs_i.reshape(-1, 2))
        E, mask = cv2.findEssentialMat(n0, ni, focal=1.0, pp=(0.0, 0.0), method=cv2.RANSAC, prob=0.999,
                                       threshold=1.5 / (s_ref * size_ref[0]))
        if E is None or E.shape[0] < 3:
            return None
        E = E[:3]
        n_in, R, t, _ = cv2.recoverPose(E, n0, ni, focal=1.0, pp=(0.0, 0.0), mask=mask)
        mi.R, mi.t = R, t.ravel()
        pts = triangulate_frames({0: obs_ref, 1: obs_i}, {0: m0, 1: mi})
        palm = np.linalg.norm(pts[:, 9] - pts[:, 0], axis=1)
        if not np.isfinite(palm).all() or np.median(palm) <= 0:
            return None
        k = palm_cm / np.median(palm)                                      # unit-length baseline to real centimetres
        return {"R": R, "t_cm": t.ravel() * k, "scale_ref": s_ref, "scale_i": s_i, "cv": bone_cv(pts),
                "inliers": int(n_in)}

    def candidates(centre=None):
        grid = FOCAL_GRID if centre is None else [round(centre + d, 3) for d in (-0.1, -0.075, -0.05, -0.025, 0, 0.025, 0.05, 0.075, 0.1)]
        return [g for g in grid if 0.4 <= g <= 1.3]

    def search(centre=None):
        best = None
        for s in candidates(centre):
            r = evaluate(s, s) if fixed_ref_scale is None else evaluate(fixed_ref_scale, s)
            if r is not None and (best is None or r["cv"] < best["cv"]):
                best = r
        return best

    coarse = search()
    if coarse is None:
        return None
    fine = search(coarse["scale_i"])
    return fine if fine is not None and fine["cv"] <= coarse["cv"] else coarse


def calibrate_from_hands(samples: list, sizes: dict, ref: int, palm_cm: float = 9.5):
    """samples: list of {cam: (21,2) px} (frames where the reference camera and at least one other saw the hand).
    Returns (models, report, volume). Raises ValueError with a plain-language reason when it cannot."""
    models = {ref: CameraModel(ref, tuple(sizes[ref]), K_for(0.8, sizes[ref]), np.zeros(5))}
    report, ref_scale = {}, None
    for i in sorted(c for c in sizes if c != ref):
        frames = [s for s in samples if ref in s and i in s]
        if len(frames) < MIN_PAIR_FRAMES:
            raise ValueError(f"camera {i} saw your hand together with camera {ref} in only {len(frames)} frames "
                             f"(need {MIN_PAIR_FRAMES}+)")
        a = np.stack([s[ref] for s in frames])
        b = np.stack([s[i] for s in frames])
        sol = solve_pair(a, b, sizes[ref], sizes[i], palm_cm, fixed_ref_scale=ref_scale)
        if sol is None:
            raise ValueError(f"could not match camera {i} to camera {ref} (move your hand more, with fingers spread)")
        if ref_scale is None:
            ref_scale = sol["scale_ref"]
            models[ref] = CameraModel(ref, tuple(sizes[ref]), K_for(ref_scale, sizes[ref]), np.zeros(5))
        models[i] = CameraModel(i, tuple(sizes[i]), K_for(sol["scale_i"], sizes[i]), np.zeros(5), sol["R"], sol["t_cm"])
        report[i] = {"bone_cv": sol["cv"], "focal_scale": sol["scale_i"], "frames": len(frames),
                     "baseline_cm": float(np.linalg.norm(sol["t_cm"]))}
    # air zone from the same waving: where the palm centre went, triangulated from every camera that saw it
    centres = []
    for s in samples:
        cams = [c for c in s if c in models]
        if len(cams) < 2:
            continue
        pts = []
        for k in PALM_IDS:
            norm = [models[c].to_normalized(s[c][k:k + 1])[0] for c in cams]
            pts.append(triangulate_nview(np.array(norm), [models[c].P() for c in cams]))
        centres.append(np.mean(pts, axis=0))
    volume = volume_from_points(np.array(centres)) if len(centres) >= 30 else None
    return models, report, volume


def quality_problem(report: dict):
    """None if the calibration looks trustworthy, otherwise a plain-language reason."""
    worst = max(r["bone_cv"] for r in report.values())
    if worst > REJECT_CV:
        return (f"the hand's bone lengths varied by {worst:.0%} in 3D (limit {REJECT_CV:.0%}), so the camera positions "
                "are not reliable. Try again with better light, rotate your hand a lot, and move it closer and farther")
    return None


class HandSampler:
    """Keeps frames where at least two cameras saw the hand AT THE SAME TIME, skipping near-duplicates."""

    def __init__(self, min_move_px: float = 8.0):
        self.min_move_px = min_move_px
        self.samples: list = []
        self._last = None

    def add(self, obs: dict) -> bool:
        if len(obs) < 2:
            return False
        key = obs[min(obs)]                                  # movement is judged on the lowest-numbered camera that saw it
        if self._last is not None and np.mean(np.linalg.norm(key - self._last, axis=1)) < self.min_move_px:
            return False
        self.samples.append(obs)
        self._last = key
        return True


# ----------------------------------------------------------------------------------------------- live session
def _put_lines(img, lines, y0, colour, scale=0.65):
    for k, line in enumerate(lines):
        cv2.putText(img, line, (12, y0 + 28 * k), cv2.FONT_HERSHEY_SIMPLEX, scale, colour, 2, cv2.LINE_AA)


def _guide_screen(frames: dict, seen: dict, lines: list, ok: bool, tile_w: int):
    """Camera pictures side by side, each framed GREEN (sees your hand) or RED (does not), with big instructions below."""
    tiles = []
    for i in sorted(frames):
        f = frames[i]
        t = cv2.resize(f, (tile_w, int(f.shape[0] * tile_w / f.shape[1])))
        if i in seen:
            draw_hand(t, seen[i])
        colour = (0, 200, 0) if i in seen else (0, 0, 220)
        t = cv2.copyMakeBorder(t, 6, 6, 6, 6, cv2.BORDER_CONSTANT, value=colour)
        label = f"camera {i}: HAND SEEN" if i in seen else f"camera {i}: hand NOT seen"
        cv2.putText(t, label, (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.75, colour, 2, cv2.LINE_AA)
        tiles.append(t)
    h = max(t.shape[0] for t in tiles)
    row = np.hstack([cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in tiles])
    panel = np.zeros((34 * len(lines) + 16, row.shape[1], 3), np.uint8)
    _put_lines(panel, lines, 30, (0, 255, 0) if ok else (0, 200, 255))
    return np.vstack([row, panel])


def show_message(lines: list, ok: bool, seconds: float = 7.0, width: int = 960) -> None:
    """A message window that stays up long enough to read (any key closes it)."""
    img = np.zeros((60 + 34 * len(lines), width, 3), np.uint8)
    _put_lines(img, lines, 40, (0, 255, 0) if ok else (0, 200, 255), 0.7)
    cv2.imshow("automatic camera set-up", img)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cv2.waitKey(50) != -1:
            break


def collect_samples(mc: MultiCamera, max_seconds: float, target: int = 150, min_seconds: float = 8.0, show: bool = True):
    """Collect frames where 2+ cameras see the hand together. Keeps going (up to max_seconds) until there are
    `target` distinct frames, so you get the time you need instead of a fixed 15 s."""
    trackers = {i: HandTracker(ensure_model("models/hand_landmarker.task")) for i in mc.indices}
    sampler, sizes = HandSampler(), {}
    start = time.monotonic()
    tile_w = max(260, min(480, 1500 // len(mc.indices)))
    try:
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= max_seconds or (len(sampler.samples) >= target and elapsed >= min_seconds):
                break
            got = mc.read()
            if got is None:
                if not mc.alive:
                    break
                continue
            frames, t = got
            for i, f in frames.items():
                sizes[i] = (f.shape[1], f.shape[0])
            obs, _ = detect_views(trackers, frames, t)
            sampler.add({i: landmarks_to_px(lm, sizes[i]) for i, lm in obs.items()})
            if show:
                n_seen = len(obs)
                lines = ["WAVE YOUR HAND where ALL cameras can see it (every frame must be GREEN).",
                         "Rotate it, open and close your fingers, move it closer and farther.",
                         f"Good frames: {len(sampler.samples)}/{target}   (at least {MIN_PAIR_FRAMES} needed)   "
                         f"{max(0, max_seconds - elapsed):.0f}s left   ESC = skip"]
                if n_seen < len(mc.indices):
                    lines[0] = "Some cameras can NOT see your hand yet: move your hand into view of ALL of them."
                cv2.imshow("automatic camera set-up", _guide_screen(frames, obs, lines, n_seen >= 2, tile_w))
                if cv2.waitKey(1) & 0xFF == 27:
                    raise KeyboardInterrupt
    finally:
        for tr in trackers.values():
            tr.close()
    return sampler.samples, sizes


def auto_calibrate(indices, out_path: str, width=640, height=480, seconds=45.0, palm_cm=9.5, max_skew_s=0.06, show=True):
    """Full automatic set-up. Returns (ok, message). Saves the calibration to `out_path` only when it looks reliable."""
    mc = MultiCamera(indices, width, height, max_skew_s)
    if not mc.opened:
        mc.release()
        return False, "could not open every camera"
    try:
        samples, sizes = collect_samples(mc, seconds, show=show)
    except KeyboardInterrupt:
        if show:
            cv2.destroyAllWindows()
        return False, "skipped"
    finally:
        mc.release()
    ok, msg = _finish(samples, sizes, out_path, palm_cm)
    if show:
        show_message([("DONE: " if ok else "NOT FINISHED: ") + part for part in _wrap(msg)] +
                     ([] if ok else ["The app will continue with ONE camera this time."]), ok)
        cv2.destroyAllWindows()
    return ok, msg


def _wrap(text: str, width: int = 82) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur] if cur else lines


def _finish(samples, sizes, out_path, palm_cm):
    """Pick the reference camera, drop cameras that never saw the hand, solve, check quality, save."""
    if not samples:
        return False, ("your hand was never seen by two cameras at the same time. Point the cameras at the same space, "
                       "hold your whole hand in view of ALL of them, and keep it well lit")
    counts: dict = {}
    for s in samples:
        for c in s:
            counts[c] = counts.get(c, 0) + 1
    ref = max(counts, key=lambda c: (counts[c], -c))                       # the camera that saw your hand most
    left_out = [i for i in sizes if i != ref and sum(1 for s in samples if ref in s and i in s) < MIN_PAIR_FRAMES]
    sizes = {i: sz for i, sz in sizes.items() if i not in left_out}
    if len(sizes) < 2 or ref not in sizes:
        got = {c: n for c, n in counts.items()}
        return False, (f"only {max(counts.values())} good frames where two cameras saw your hand together (need {MIN_PAIR_FRAMES}+; "
                       f"hand sightings per camera: {got}). Move your hand where ALL cameras can see the whole hand "
                       "at once, or aim the cameras at the same area")
    samples = [{c: v for c, v in s.items() if c in sizes} for s in samples]
    try:
        models, report, volume = calibrate_from_hands(samples, sizes, ref, palm_cm)
    except ValueError as exc:
        return False, str(exc)
    problem = quality_problem(report)
    if problem:
        return False, problem
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.replace(path.with_suffix(".bak.json"))
    save_calibration(out_path, models, ref, {"source": "hand", "palm_cm": palm_cm, "quality": report}, volume)
    worst = max(r["bone_cv"] for r in report.values())
    note = "" if worst <= WARN_CV else " (fair quality: for better accuracy use the checkerboard route)"
    cams = ", ".join(f"camera {i} is {r['baseline_cm']:.0f} cm from camera {ref}" for i, r in report.items())
    skipped = f". Left out cameras {left_out} (they did not see your hand)" if left_out else ""
    return True, f"{len(models)} cameras calibrated ({cams}); bone-length consistency {worst:.0%}{note}{skipped}"


def main() -> None:
    ap = argparse.ArgumentParser(prog="autocal")
    ap.add_argument("--cameras", help="comma-separated camera indices (default: scan for all)")
    ap.add_argument("--seconds", type=float, default=45.0, help="the longest it will wait for enough good frames")
    ap.add_argument("--palm-cm", type=float, default=9.5, help="your wrist-to-middle-knuckle length (sets the real-world scale)")
    ap.add_argument("--out", default="data/stereo_calibration.json")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    args = ap.parse_args()
    indices = [int(x) for x in args.cameras.split(",")] if args.cameras else [c["index"] for c in scan_cameras()]
    print("Cameras:", indices)
    if len(indices) < 2:
        raise SystemExit("Stereo needs at least 2 cameras.")
    ok, msg = auto_calibrate(indices, args.out, args.width, args.height, args.seconds, args.palm_cm)
    print(("Done: " if ok else "Not saved: ") + msg)


if __name__ == "__main__":
    main()
