"""One-time stereo setup for 2 or more cameras.

    python -m gesture_control.stereo_calibrate --make-board     # writes data/checkerboard_9x6.png to print
    python -m gesture_control.stereo_calibrate --square-cm 2.5  # calibrate (measure one printed square in cm!)
    python -m gesture_control.stereo_calibrate --volume-only    # redo just the 3D "air zone"

Step 1 (cameras): hold the printed checkerboard where the cameras can see it, flat and still-ish, and move it
around: closer/farther, tilted, left/right. It captures views by itself (ESC to finish early).
Step 2 (air zone): move your hand around the area you want to use for ~15 s; hands outside that 3D box are ignored.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from .cameras import MultiCamera, scan_cameras
from .stereo import (board_points, calibrate_rig, detect_views, find_board, fuse_hand, load_calibration, save_calibration,
                     volume_from_points)
from .tracker import HandTracker, ensure_model


def make_board_png(path: str, cols: int, rows: int, square_px: int = 100, margin_px: int = 100) -> None:
    """A (cols+1) x (rows+1) squares checkerboard, which has cols x rows inner corners."""
    h, w = (rows + 1) * square_px + 2 * margin_px, (cols + 1) * square_px + 2 * margin_px
    img = np.full((h, w), 255, np.uint8)
    for r in range(rows + 1):
        for c in range(cols + 1):
            if (r + c) % 2 == 0:
                y, x = margin_px + r * square_px, margin_px + c * square_px
                img[y:y + square_px, x:x + square_px] = 0
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(path, img)


def _tile(frames: dict, width: int = 360):
    tiles = []
    for i in sorted(frames):
        f = frames[i]
        s = width / f.shape[1]
        t = cv2.resize(f, (width, int(f.shape[0] * s)))
        cv2.putText(t, f"cam {i}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        tiles.append(t)
    h = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in tiles]
    return np.hstack(tiles)


def capture_board_views(mc, cols, rows, want, ref):
    views, sizes, last_ref_corners, last_t = [], {}, None, 0.0
    while len(views) < want:
        got = mc.read()
        if got is None:
            continue
        frames, t = got
        seen = {}
        shown = {}
        for i, f in frames.items():
            sizes[i] = (f.shape[1], f.shape[0])
            corners = find_board(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cols, rows)
            shown[i] = f.copy()
            if corners is not None:
                seen[i] = corners
                cv2.drawChessboardCorners(shown[i], (cols, rows), corners.reshape(-1, 1, 2).astype(np.float32), True)
        ok_view = ref in seen and len(seen) >= 2
        moved = last_ref_corners is None or (ok_view and np.mean(np.linalg.norm(seen[ref] - last_ref_corners, axis=1)) > 25)
        if ok_view and moved and t - last_t > 0.7:
            views.append(seen)
            last_ref_corners, last_t = seen[ref], t
        tile = _tile(shown)
        msg = f"views {len(views)}/{want}   board seen by cams {sorted(seen)}   (ESC = finish)"
        cv2.putText(tile, msg, (8, tile.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if ok_view else (0, 0, 255), 2)
        cv2.imshow("stereo calibration", tile)
        if cv2.waitKey(1) & 0xFF == 27:
            break
    return views, sizes


def capture_volume(mc, models, ref, seconds):
    trackers = {i: HandTracker(ensure_model("models/hand_landmarker.task")) for i in models}
    pts, end = [], time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            got = mc.read()
            if got is None:
                continue
            frames, t = got
            obs, _ = detect_views(trackers, {i: f for i, f in frames.items() if i in models}, t)
            hand = fuse_hand(obs, models, ref) if len(obs) >= 2 else None
            if hand is not None:
                pts.append(hand.center())
            shown = {i: f.copy() for i, f in frames.items()}
            tile = _tile(shown)
            cv2.putText(tile, f"move your hand around the area you will use: {max(0, end - time.monotonic()):.0f}s   3D samples: {len(pts)}",
                        (8, tile.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("stereo calibration", tile)
            if cv2.waitKey(1) & 0xFF == 27:
                break
    finally:
        for tr in trackers.values():
            tr.close()
    return np.array(pts)


def main() -> None:
    ap = argparse.ArgumentParser(prog="stereo_calibrate")
    ap.add_argument("--cameras", help="comma-separated camera indices (default: scan for all)")
    ap.add_argument("--cols", type=int, default=9, help="inner corners across the board")
    ap.add_argument("--rows", type=int, default=6, help="inner corners down the board")
    ap.add_argument("--square-cm", type=float, default=2.5, help="side of ONE printed square, measured with a ruler")
    ap.add_argument("--views", type=int, default=25)
    ap.add_argument("--volume-seconds", type=int, default=15)
    ap.add_argument("--out", default="data/stereo_calibration.json")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--make-board", action="store_true", help="write a printable checkerboard PNG and exit")
    ap.add_argument("--volume-only", action="store_true", help="keep the camera calibration, redo only the air zone")
    args = ap.parse_args()

    if args.make_board:
        path = f"data/checkerboard_{args.cols}x{args.rows}.png"
        make_board_png(path, args.cols, args.rows)
        print(f"Wrote {path}. Print it at 100% scale (no 'fit to page'), glue it flat, and MEASURE one square with a ruler.")
        print(f"Then run: python -m gesture_control.stereo_calibrate --square-cm <that measurement>")
        return

    indices = [int(x) for x in args.cameras.split(",")] if args.cameras else [c["index"] for c in scan_cameras()]
    print("Cameras:", indices)
    if len(indices) < 2:
        raise SystemExit("Stereo needs at least 2 cameras. Connect another one (each on its own USB port) and try again.")
    mc = MultiCamera(indices, args.width, args.height)
    if not mc.opened:
        raise SystemExit("Could not open every camera.")
    try:
        if args.volume_only:
            models, ref, _, board = load_calibration(args.out)
            models = {i: m for i, m in models.items() if i in indices}
        else:
            ref = indices[0]
            views, sizes = capture_board_views(mc, args.cols, args.rows, args.views, ref)
            obj = board_points(args.cols, args.rows, args.square_cm)
            usable = dict(sizes)
            while True:                              # drop cameras that did not see the board enough, keep the rest
                try:
                    models = calibrate_rig(views, obj, usable, ref)
                    break
                except ValueError as exc:
                    print("Problem:", exc)
                    bad = [i for i in usable if i != ref and sum(1 for v in views if i in v and ref in v) < 8]
                    if not bad:
                        raise SystemExit("Could not calibrate. Show the board to the reference camera and the others together, "
                                         "in more positions and angles, then try again.")
                    for i in bad:
                        print(f"  leaving camera {i} out (it rarely saw the board together with camera {ref})")
                        usable.pop(i)
                    if len(usable) < 2:
                        raise SystemExit("Not enough cameras saw the board together.")
            for i, rep in calibrate_rig.last_report.items():
                if isinstance(rep, tuple):
                    base = float(np.linalg.norm(models[i].t))
                    print(f"  camera {i}: lens fit {rep[0]:.2f} px, pair fit {rep[1]:.2f} px, {base:.1f} cm from camera {ref}"
                          + ("   <-- high: redo with more varied board positions" if max(rep) > 1.5 else ""))
                else:
                    print(f"  camera {i} (reference): lens fit {rep:.2f} px")
            board = {"source": "checkerboard", "cols": args.cols, "rows": args.rows, "square_cm": args.square_cm}
        cv2.destroyAllWindows()
        print(f"\nNow the air zone: for {args.volume_seconds} s move your hand around the area you want to use "
              "(raise it, lower it, left, right). Hands outside this 3D box will be ignored.")
        pts = capture_volume(mc, models, ref, args.volume_seconds)
        volume = None
        if len(pts) >= 30:
            volume = volume_from_points(pts)
            print("Air zone (cm, reference camera frame):", [round(v) for v in volume["min"]], "to", [round(v) for v in volume["max"]])
        else:
            print(f"Only {len(pts)} 3D hand samples (need 30+): no air zone saved. The normal 2D air gate will be used. "
                  "Make sure your hand is visible to 2+ cameras and run again with --volume-only.")
        save_calibration(args.out, models, ref, board, volume)
        print(f"\nSaved {args.out}. Run the app normally: python -m gesture_control --rule")
    finally:
        mc.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
