"""MediaPipe hand landmark detection (Tasks API, VIDEO mode)."""
from __future__ import annotations

import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


def ensure_model(path: str | Path) -> Path:
    path = Path(path)
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(MODEL_URL, path)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Download the hand model from {MODEL_URL} and save it as {path}") from exc
    return path


class HandTracker:
    """Detects one hand. Feed it MIRRORED frames so the handedness label is the user's real hand."""

    def __init__(self, model_path):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        self._landmarker = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
            )
        )
        self._last = -1

    def detect(self, frame_bgr, timestamp_ms: int):
        """Return (landmarks, label, confidence) for the best hand, or None."""
        import cv2

        self._last = max(timestamp_ms, self._last + 1)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        res = self._landmarker.detect_for_video(image, self._last)
        if not res.hand_landmarks:
            return None
        return res.hand_landmarks[0], res.handedness[0][0].category_name, float(res.handedness[0][0].score)

    def close(self):
        self._landmarker.close()
