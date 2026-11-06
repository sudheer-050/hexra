"""Record your own examples of each pose (about 5 minutes total, at your own pace).

For every pose: read the description, make the pose, press SPACE to record (~80 samples), and
slowly move/tilt your hand and change distance a little while it records.
Keys: SPACE record | N skip | B back | ESC finish.   Run it again later to add a second session.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import cv2

from .features import normalize
from .poses import POSE_HELP, POSES
from .tracker import HandTracker, ensure_model

SAVE_EVERY = 3


def draw_hand(frame, landmarks):
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
             (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]
    h, w = frame.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in landmarks]
    for a, b in edges:
        cv2.line(frame, pts[a], pts[b], (0, 255, 255), 2)
    for pt in pts:
        cv2.circle(frame, pt, 4, (0, 255, 0), -1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", default=",".join(POSES))
    ap.add_argument("--samples", type=int, default=80)
    ap.add_argument("--out", default="data/poses.csv")
    args = ap.parse_args()
    poses = [p for p in args.poses.split(",") if p in POSES]

    tracker = HandTracker(ensure_model("models/hand_landmarker.task"))
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit("Could not open the webcam.")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    session = time.strftime("%Y%m%d-%H%M%S")
    saved: dict[str, int] = {}
    idx, recording, got, frame_i = 0, False, 0, 0

    with out.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["label", "session"] + [f"f{i}" for i in range(63)])
        while 0 <= idx < len(poses):
            pose = poses[idx]
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            det = tracker.detect(frame, int(time.monotonic() * 1000))
            frame_i += 1
            if det:
                draw_hand(frame, det[0])
            if recording and det and frame_i % SAVE_EVERY == 0:
                try:
                    w.writerow([pose, session, *normalize(*det).tolist()])
                    got += 1
                    saved[pose] = saved.get(pose, 0) + 1
                except ValueError:
                    pass
            if recording and got >= args.samples:
                recording, got, idx = False, 0, idx + 1
                continue
            if recording:
                msg, col = f"RECORDING {pose.upper()}  {got}/{args.samples}  (move/tilt slightly)", (0, 255, 0)
            elif det:
                msg, col = f"{pose.upper()}: {POSE_HELP[pose]}", (0, 255, 255)
            else:
                msg, col = f"{pose.upper()}: no hand found - show your hand", (0, 0, 255)
            cv2.putText(frame, msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
            cv2.putText(frame, f"{idx + 1}/{len(poses)}   SPACE record   N skip   B back   ESC finish",
                        (10, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow("calibrate", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            if key == 32 and not recording:
                recording, got = True, 0
            elif key in (ord("n"), ord("N")):
                recording, got, idx = False, 0, idx + 1
            elif key in (ord("b"), ord("B")):
                recording, got, idx = False, 0, max(0, idx - 1)
    cap.release()
    tracker.close()
    cv2.destroyAllWindows()
    print(f"Saved {sum(saved.values())} samples: {saved}. Now run: python -m hexra.train")


if __name__ == "__main__":
    main()
