"""Enrol the ADMIN face (once). Only numeric face fingerprints are stored; no photos.

    python -m hexra.enroll_face            # enrol (asks before downloading the face models)
    python -m hexra.enroll_face --add      # add more samples (e.g. with glasses, other lighting)
    python -m hexra.enroll_face --clear    # forget the admin completely

Only YOU should be in the picture while enrolling: samples are taken only when exactly one face is visible.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from .camera import ThreadedCamera
from .face_lock import (DEFAULTS, FaceLock, OpenCVFaceAnalyzer, download_models, load_admin, models_missing, save_admin)

PROMPTS = ["Look straight at the camera", "Turn your head a little to the LEFT", "Turn a little to the RIGHT",
           "Tilt your chin UP a little", "Tilt your chin DOWN a little", "Look straight and smile"]
MIN_FACE_SCORE, MIN_FACE_PX = 0.9, 90


def run_enrollment(admin_file: str = DEFAULTS["admin_file"], samples: int = 18, camera: int = 0, width: int = 640,
                   height: int = 480, assume_yes: bool = False, add: bool = False, max_seconds: float = 120.0) -> bool:
    if not download_models(assume_yes):
        return False
    analyzer = OpenCVFaceAnalyzer()
    cap = ThreadedCamera(camera, width, height)
    if not cap.opened:
        print("Could not open the camera (is another copy of the app running?).")
        return False
    collected, last, start = [], 0.0, time.monotonic()
    cancelled = False
    try:
        while len(collected) < samples and time.monotonic() - start < max_seconds:
            got = cap.read()
            if got is None:
                if not cap.alive:
                    break
                continue
            frame, t = got
            frame = cv2.flip(frame, 1)
            faces = analyzer(frame)
            good = [f for f in faces if f[1] >= MIN_FACE_SCORE and f[2][2] >= MIN_FACE_PX]
            if len(faces) != 1:
                msg, colour = ("No face found: move into view" if not faces else "Only YOU should be in view"), (0, 0, 255)
            elif not good:
                msg, colour = "Move a little closer / face the light", (0, 165, 255)
            else:
                prompt = PROMPTS[min(len(collected) * len(PROMPTS) // samples, len(PROMPTS) - 1)]
                msg, colour = prompt, (0, 255, 0)
                if t - last >= 0.7:
                    collected.append(good[0][0])
                    last = t
            for _, _, (x, y, w, h) in faces:
                cv2.rectangle(frame, (int(x), int(y)), (int(x + w), int(y + h)), colour, 2)
            cv2.putText(frame, f"ENROLLING ADMIN FACE   {len(collected)}/{samples}   (ESC = cancel)", (10, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, msg, (10, frame.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)
            cv2.imshow("enrol admin face", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                cancelled = True
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    if cancelled:
        print("Cancelled: nothing saved.")
        return False
    if len(collected) < max(6, samples // 2):
        print(f"Only {len(collected)} usable samples were captured (need at least {max(6, samples // 2)}). "
              "Make sure only you are in view, your face is lit and fills a good part of the picture.")
        return False
    emb = np.stack(collected)
    sims = emb @ emb.T
    off = sims[~np.eye(len(emb), dtype=bool)]
    print(f"Captured {len(emb)} samples. How alike they are to each other: average {off.mean():.2f}, lowest {off.min():.2f} "
          f"(good enrolments are above about 0.5).")
    if add:
        old = load_admin(admin_file)
        if old is not None:
            emb = np.vstack([old, emb])
    save_admin(admin_file, emb)
    print(f"Saved {len(emb)} fingerprints to {admin_file} (numbers only, no photos).")
    return True


def build_face_lock(opts: dict) -> FaceLock:
    """Make the lock for the app. If nobody is enrolled yet, enrol now. Stops the app (fails closed) if that is refused."""
    admin_file = opts["admin_file"]
    if load_admin(admin_file) is None:
        print("Face lock is ON, but no admin face is enrolled yet. Starting enrolment (look at the camera)...")
        if not run_enrollment(admin_file):
            raise SystemExit("Face lock: no admin face enrolled, so the app will not run.\n"
                             "  Enrol with:  python -m hexra.enroll_face\n"
                             "  or run once without the lock:  python -m hexra --no-face-lock")
    if models_missing() and not download_models():
        raise SystemExit("Face lock: the face models are missing and were not downloaded. "
                         "Run python -m hexra.enroll_face, or start with --no-face-lock.")
    return FaceLock(OpenCVFaceAnalyzer(), load_admin(admin_file), threshold=float(opts["threshold"]),
                    check_every_s=float(opts["check_every_s"]), grace_s=float(opts["grace_s"]),
                    require_face=bool(opts["require_face"]))


def main() -> None:
    ap = argparse.ArgumentParser(prog="enroll_face")
    ap.add_argument("--samples", type=int, default=18)
    ap.add_argument("--file", default=DEFAULTS["admin_file"])
    ap.add_argument("--add", action="store_true", help="keep the existing admin and add more samples")
    ap.add_argument("--clear", action="store_true", help="delete the saved admin face and exit")
    ap.add_argument("--yes", action="store_true", help="download the face models without asking")
    args = ap.parse_args()
    if args.clear:
        p = Path(args.file)
        print(f"Deleted {p}." if p.exists() else "Nothing to delete.")
        p.unlink(missing_ok=True)
        return
    ok = run_enrollment(args.file, args.samples, assume_yes=args.yes, add=args.add)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
