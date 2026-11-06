"""Face lock: gestures only work while the ADMIN's face is recognised in the camera picture.

* Enrolment (python -m hexra.enroll_face) stores only a numeric "face fingerprint" (128 numbers per sample)
  in data/admin_face.npz. No photos are saved.
* While the app runs, a background thread looks at the newest picture every few tenths of a second, compares every face
  with the admin's, and the control loop only asks "is the admin here?" (no waiting, so the cursor is never delayed).
* The admin counts as present for `grace_s` seconds after the last match (looking down or away briefly is fine).

Honest limits: this is a convenience lock, not strong security. A photo or video of the admin held to the camera can fool
it (there is no liveness check), and it identifies a FACE, not whose hand is moving.
"""
from __future__ import annotations

import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

MODELS = {
    "detector": {
        "path": "models/face_detection_yunet_2023mar.onnx",
        "url": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
        "approx_mb": 0.23, "min_bytes": 200_000,
    },
    "recognizer": {
        "path": "models/face_recognition_sface_2021dec.onnx",
        "url": "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
        "approx_mb": 38.7, "min_bytes": 30_000_000,
    },
}

DEFAULTS = {
    "enabled": True,
    "admin_file": "data/admin_face.npz",
    "threshold": 0.363,        # cosine similarity needed to count as the admin (OpenCV's recommended value for SFace)
    "check_every_s": 0.4,      # how often a picture is checked (on a background thread)
    "grace_s": 3.0,            # the admin counts as present this long after the last match
    "require_face": True,      # True: locked whenever no recognised admin is seen. False: only an UNKNOWN face locks it
}


def normalize_rows(a: np.ndarray) -> np.ndarray:
    a = np.atleast_2d(np.asarray(a, dtype=np.float32))
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)


def save_admin(path: str, embeddings: np.ndarray) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, embeddings=normalize_rows(embeddings), created=time.strftime("%Y-%m-%d %H:%M:%S"))


def load_admin(path: str):
    """The saved admin fingerprints (N,128), or None if nobody is enrolled."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = np.load(p)
        emb = normalize_rows(data["embeddings"])
        return emb if len(emb) else None
    except Exception:
        return None


def models_missing() -> list:
    return [k for k, m in MODELS.items() if not Path(m["path"]).exists() or Path(m["path"]).stat().st_size < m["min_bytes"]]


def download_models(assume_yes: bool = False, ask=input, say=print) -> bool:
    """Download the face models that are missing, asking first. Returns True when all models are present."""
    missing = models_missing()
    if not missing:
        return True
    say("The face lock needs these model files (OpenCV's official models, open source, hosted on Hugging Face):")
    for k in missing:
        say(f"  {MODELS[k]['path']}   about {MODELS[k]['approx_mb']} MB   from {MODELS[k]['url']}")
    if not assume_yes and ask("Download them now? [y/N] ").strip().lower() not in ("y", "yes"):
        say("Not downloaded.")
        return False
    for k in missing:
        m = MODELS[k]
        path = Path(m["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        try:
            say(f"  downloading {path.name} ...")
            urllib.request.urlretrieve(m["url"], tmp)
            if tmp.stat().st_size < m["min_bytes"]:
                raise OSError(f"downloaded file is only {tmp.stat().st_size} bytes (expected about {m['approx_mb']} MB)")
            tmp.replace(path)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            say(f"  failed: {exc}")
            if "WRONG_VERSION_NUMBER" in str(exc) or "SSL" in str(exc):
                say("  (a network/proxy/antivirus problem with HTTPS; try another network, or download the file in your "
                    f"browser from {m['url']} and save it as {m['path']})")
            return False
    return True


class OpenCVFaceAnalyzer:
    """frame (BGR) -> [(fingerprint (128,), detection score, (x, y, w, h)), ...] using OpenCV's YuNet + SFace."""

    def __init__(self, detector_path: str | None = None, recognizer_path: str | None = None, min_score: float = 0.8):
        import cv2

        self._cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(detector_path or MODELS["detector"]["path"], "", (320, 320), min_score, 0.3, 5)
        self.recognizer = cv2.FaceRecognizerSF.create(recognizer_path or MODELS["recognizer"]["path"], "")
        self._size = None

    def __call__(self, frame) -> list:
        h, w = frame.shape[:2]
        if self._size != (w, h):
            self.detector.setInputSize((w, h))
            self._size = (w, h)
        _, faces = self.detector.detect(frame)
        out = []
        if faces is None:
            return out
        for row in faces:
            aligned = self.recognizer.alignCrop(frame, row)
            feat = np.asarray(self.recognizer.feature(aligned), dtype=np.float32).reshape(-1)
            out.append((feat / max(float(np.linalg.norm(feat)), 1e-9), float(row[14]), tuple(float(v) for v in row[:4])))
        return out


class FaceLock:
    def __init__(self, analyzer, admin, threshold=0.363, check_every_s=0.4, grace_s=3.0, require_face=True, threaded=True):
        self.analyzer = analyzer
        self.admin = normalize_rows(admin)
        self.threshold, self.check_every_s, self.grace_s = threshold, check_every_s, grace_s
        self.require_face = require_face
        self.last_admin = None        # when the admin was last recognised
        self.last_unknown = None      # when a face that is NOT the admin was last seen
        self.faces = 0
        self.best = 0.0               # best similarity in the last picture checked
        self._last_check = -1e9
        self._threaded = threaded
        self._cond = threading.Condition()
        self._pending = None
        self._stop = False
        if threaded:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    # ---- called by the control loop (never blocks) ----
    def submit(self, frame, t: float) -> None:
        if t - self._last_check < self.check_every_s:
            return
        self._last_check = t
        if not self._threaded:
            self._analyze(frame, t)
            return
        with self._cond:
            if self._pending is None:                  # the worker is idle; otherwise skip this picture
                self._pending = (frame.copy(), t)
                self._cond.notify()

    def allowed(self, t: float) -> bool:
        if self.last_admin is not None and t - self.last_admin <= self.grace_s:
            return True
        if not self.require_face:                      # lenient: block only while a stranger is in view
            return self.last_unknown is None or t - self.last_unknown > self.grace_s
        return False

    def describe(self, t: float) -> str:
        if self.allowed(t) and self.last_admin is not None and t - self.last_admin <= self.grace_s:
            return f"face lock: ADMIN recognised ({self.best:.2f})"
        if self.faces == 0:
            return "face lock: LOCKED - no face in view"
        return f"face lock: LOCKED - not the admin (best match {self.best:.2f}, needs {self.threshold:.2f})"

    # ---- the worker ----
    def _analyze(self, frame, t: float) -> None:
        results = self.analyzer(frame)
        best, admin_seen = 0.0, False
        for emb, _score, _box in results:
            sim = float(np.max(self.admin @ normalize_rows(emb)[0]))
            best = max(best, sim)
            if sim >= self.threshold:
                admin_seen = True
                self.last_admin = t
            else:
                self.last_unknown = t
        self.faces, self.best = len(results), best

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._pending is not None or self._stop, 0.2)
                if self._stop:
                    return
                job, self._pending = self._pending, None
            if job is not None:
                try:
                    self._analyze(*job)
                except Exception:
                    pass

    def close(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        if self._threaded:
            self._thread.join(timeout=1.0)
