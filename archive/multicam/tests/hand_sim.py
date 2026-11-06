"""A simulated articulated hand (constant bone lengths) seen by simulated cameras."""
import cv2
import numpy as np

from gesture_control.autocal import K_for
from gesture_control.stereo import CameraModel

W, H = 640, 480
TRUE_SCALE = 0.85          # the simulated cameras' real focal length / image width

FINGERS = {   # name: (knuckle position in the palm plane, segment lengths)
    "index": ((-3.0, 9.0, 0.0), (4.0, 2.4, 2.0)),
    "middle": ((0.0, 9.5, 0.0), (4.4, 2.7, 2.1)),
    "ring": ((3.0, 9.0, 0.0), (4.0, 2.6, 2.0)),
    "pinky": ((5.5, 7.5, 0.0), (3.2, 1.8, 1.8)),
}
IDS = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20)}


def _rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def hand_points(rng):
    """21 landmark positions (cm) in the hand's own frame, with a random finger pose. Wrist -> middle knuckle = 9.5 cm."""
    p = np.zeros((21, 3))
    for name, (knuckle, segs) in FINGERS.items():
        ids = IDS[name]
        p[ids[0]] = knuckle
        spread = _rz(rng.uniform(-0.15, 0.15))
        flex = np.cumsum([rng.uniform(0.0, 1.2), rng.uniform(0.0, 1.6), rng.uniform(0.0, 1.0)])
        pos = np.array(knuckle, float)
        for k, length in enumerate(segs):
            direction = spread @ _rx(-flex[k]) @ np.array([0.0, 1.0, 0.0])
            pos = pos + length * direction
            p[ids[k + 1]] = pos
    base = np.array([-3.5, 2.0, 0.5])
    p[1] = base
    pos, ang = base, rng.uniform(0.0, 0.9)
    for k, length in enumerate((3.5, 3.0, 2.5)):
        direction = _rz(0.9 + 0.5 * rng.uniform(-1, 1)) @ _rx(-ang * (k + 1) / 3) @ np.array([0.0, 1.0, 0.0])
        pos = pos + length * direction
        p[2 + k] = pos
    return p


def world_hand(rng):
    """A hand with random orientation about 40-65 cm in front of camera 0."""
    R, _ = cv2.Rodrigues(rng.normal(0, 0.55, 3))
    centre = np.array([rng.uniform(-8, 8), rng.uniform(-6, 6), rng.uniform(40, 65)])
    return (hand_points(rng) - np.array([0, 5.0, 0])) @ R.T + centre


def make_rig(n=2, baseline=18.0, scale=TRUE_SCALE):
    """Camera 0 at the origin; the others to its sides, toed in toward a point 50 cm ahead."""
    models = {0: CameraModel(0, (W, H), K_for(scale, (W, H)), np.zeros(5))}
    for k in range(1, n):
        side = baseline * k * (1 if k % 2 else -1)
        a = np.arctan2(side, 50.0)
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        models[k] = CameraModel(k, (W, H), K_for(scale, (W, H)), np.zeros(5), R, -R @ np.array([side, 0.0, 0.0]))
    return models


def simulate_samples(models, n_frames, rng, noise_px=1.0):
    """Frames where every camera sees the hand: [{cam: (21,2) px}, ...] and the true 3D points."""
    samples, truth = [], []
    while len(samples) < n_frames:
        X = world_hand(rng)
        obs = {}
        for i, m in models.items():
            px = m.project(X) + rng.normal(0, noise_px, (21, 2))
            if (px[:, 0] > 0).all() and (px[:, 0] < W).all() and (px[:, 1] > 0).all() and (px[:, 1] < H).all():
                obs[i] = px
        if len(obs) == len(models):
            samples.append(obs)
            truth.append(X)
    return samples, np.array(truth)
