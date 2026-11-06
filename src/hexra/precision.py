"""Measure how steady the cursor point is on YOUR hand and camera.

    python -m hexra.precision                 # hold your open hand still for 8 s when it says GO
    python -m hexra.precision --width 1280 --height 720     # compare camera sizes

Both candidate cursor points (the index knuckle alone, and the average of the four knuckles) are computed from the very
same frames, so the comparison is fair. Numbers are in SCREEN PIXELS at your config's screen size and active box, i.e.
how much the cursor would shake if it simply copied your hand. Lower = steadier. Nothing is saved except these numbers.
"""
from __future__ import annotations

import argparse
import time

import numpy as np

from .app import load_config
from .camera import ThreadedCamera
from .screen import enable_dpi_awareness
from .tracker import HandTracker, ensure_model

KNUCKLES = (5, 9, 13, 17)


def spread(px: np.ndarray) -> str:
    sd = px.std(axis=0)
    ptp = np.ptp(px, axis=0)
    return f"std {np.hypot(*sd):5.1f} px | peak-to-peak x {ptp[0]:5.1f}  y {ptp[1]:5.1f}"


def main() -> None:
    ap = argparse.ArgumentParser(prog="precision")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    enable_dpi_awareness()
    cfg = load_config(args.config)
    x0, y0, x1, y1 = cfg.region
    sx, sy = cfg.screen_w / (x1 - x0), cfg.screen_h / (y1 - y0)       # screen px per unit of hand movement

    cap = ThreadedCamera(0, args.width, args.height)
    if not cap.opened:
        raise SystemExit("Could not open the camera (is the app still running?).")
    tracker = HandTracker(ensure_model("models/hand_landmarker.task"))
    try:
        print("Hold your OPEN hand up in front of the camera and keep it as STILL as you can.")
        for n in (3, 2, 1):
            print(f"  starting in {n} ...")
            time.sleep(1)
        print("  GO - hold still!")
        index, avg, frames, start = [], [], 0, time.monotonic()
        size = None
        while time.monotonic() - start < args.seconds:
            got = cap.read()
            if got is None:
                continue
            frame, t = got
            size = (frame.shape[1], frame.shape[0])
            frames += 1
            det = tracker.detect(frame, int(t * 1000))
            if not det:
                continue
            lm = det[0]
            index.append((lm[5].x * sx, lm[5].y * sy))
            avg.append((sum(lm[i].x for i in KNUCKLES) / 4 * sx, sum(lm[i].y for i in KNUCKLES) / 4 * sy))
    finally:
        cap.release()
        tracker.close()

    skip = int(len(index) * 0.1)                                      # ignore the settling at the start
    if len(index) - skip < 30:
        raise SystemExit(f"Only {len(index)} frames with a hand out of {frames}: keep your open hand in view and try again.")
    a, b = np.array(index[skip:]), np.array(avg[skip:])
    print(f"\ncamera picture {size[0]}x{size[1]}, hand seen in {len(index)}/{frames} frames")
    print(f"  index knuckle only        : {spread(a)}")
    print(f"  average of 4 knuckles     : {spread(b)}")
    ratio = np.hypot(*b.std(axis=0)) / max(np.hypot(*a.std(axis=0)), 1e-9)
    print(f"  -> the knuckle average shakes {ratio:.0%} as much as the single point "
          f"({'steadier' if ratio < 0.95 else 'about the same'}).")
    print("Includes your own hand tremor, so treat it as a comparison, not an absolute. Try again with --width 1280 --height 720.")


if __name__ == "__main__":
    main()
