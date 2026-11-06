"""Air gate: gestures only count while your hand is deliberately raised in the air.

Two checks:
1. IN THE AIR: the whole hand is inside the camera frame (not cut off at an edge) and its centre is in the
   upper part of the picture. A hand resting on a desk, lap or keyboard sits low or is partly out of frame.
2. AWAKE: the system starts asleep. Hold an open palm in the air for `wake_seconds` to wake it. It goes back
   to sleep after the hand has been out of the air zone for `sleep_seconds`.
"""
from __future__ import annotations

KNUCKLES = (5, 9, 13, 17)


class AirGate:
    def __init__(self, enabled: bool = True, wake_seconds: float = 1.0, sleep_seconds: float = 1.0,
                 max_center_y: float = 0.72, edge_margin: float = 0.02, wake_pose: str = "palm"):
        self.enabled = enabled
        self.wake_seconds, self.sleep_seconds = wake_seconds, sleep_seconds
        self.max_center_y, self.edge_margin, self.wake_pose = max_center_y, edge_margin, wake_pose
        self.awake = not enabled
        self._hold_start = None
        self._last_air = 0.0
        self.wake_progress = 0.0   # 0..1, for the on-screen overlay

    def in_air(self, landmarks, relaxed: bool = False) -> bool:
        """relaxed (while you are dragging): only the hand centre must be inside the frame and not at the very
        bottom, so reaching to the screen edge does not drop what you hold."""
        if landmarks is None:
            return False
        cx = sum(landmarks[i].x for i in KNUCKLES) / len(KNUCKLES)      # the same point as the ball in the camera window
        cy = sum(landmarks[i].y for i in KNUCKLES) / len(KNUCKLES)
        if relaxed:
            return 0.0 <= cx <= 1.0 and 0.0 <= cy <= 0.97
        m = self.edge_margin
        for p in landmarks:
            if not (m <= p.x <= 1 - m and m <= p.y <= 1 - m):
                return False                      # part of the hand is outside the frame
        return cy <= self.max_center_y              # the ball must be above the blue line

    def update(self, landmarks, pose, t: float, holding: bool = False) -> bool:
        """Return True when gestures should be processed this frame."""
        if not self.enabled:
            return landmarks is not None
        air = self.in_air(landmarks, relaxed=holding and self.awake)
        if air:
            self._last_air = t
        if self.awake:
            if not air and t - self._last_air > self.sleep_seconds:
                self.awake = False
                self._hold_start, self.wake_progress = None, 0.0
            return self.awake and air
        if air and pose == self.wake_pose:
            if self._hold_start is None:
                self._hold_start = t
            self.wake_progress = min((t - self._hold_start) / self.wake_seconds, 1.0)
            if self.wake_progress >= 1.0:
                self.awake, self._hold_start, self.wake_progress = True, None, 0.0
        else:
            self._hold_start, self.wake_progress = None, 0.0
        return False
