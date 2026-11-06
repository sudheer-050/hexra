"""Stereo math tested with SIMULATED cameras at known positions (no real cameras needed)."""
import cv2
import numpy as np
import pytest

from hexra.stereo import (CameraModel, board_points, calibrate_rig, fuse_hand, load_calibration, rebase,
                                    rebase_volume, save_calibration, triangulate_nview, volume_contains,
                                    volume_from_points)

W, H, F = 640, 480, 600.0
K = np.array([[F, 0, W / 2], [0, F, H / 2], [0, 0, 1.0]])
NODIST = np.zeros(5)


def rot_y(deg):
    a = np.deg2rad(deg)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])


def make_rig(n=3):
    """Camera 0 at the origin looking forward; the others sit to the side, toed in toward the hand at ~50 cm depth."""
    models = {0: CameraModel(0, (W, H), K, NODIST)}
    for k in range(1, n):
        side = 18.0 * k * (1 if k % 2 else -1)           # cm to the right / left of camera 0
        yaw = np.rad2deg(np.arctan2(side, 50.0))         # toe in toward a point 50 cm ahead
        R = rot_y(yaw)
        c_world = np.array([side, 0.0, 0.0])             # camera centre in the world frame
        models[k] = CameraModel(k, (W, H), K, NODIST, R, -R @ c_world)
    return models


def fake_hand(rng):
    """21 points inside a ~10 cm cube, about 50 cm in front of camera 0."""
    return np.array([0.0, 0.0, 50.0]) + rng.uniform(-5, 5, (21, 3))


def observe(models, pts, noise_px=0.0, rng=None):
    obs = {}
    for i, m in models.items():
        px = m.project(pts)
        if noise_px:
            px = px + rng.normal(0, noise_px, px.shape)
        obs[i] = [type("L", (), {"x": u / m.size[0], "y": v / m.size[1]})() for u, v in px]
    return obs


@pytest.mark.parametrize("n_cams", [2, 3, 4])
def test_triangulation_recovers_3d_points_with_any_number_of_cameras(n_cams):
    rng = np.random.default_rng(0)
    models = make_rig(n_cams)
    pts = fake_hand(rng)
    hand = fuse_hand(observe(models, pts, noise_px=0.5, rng=rng), models, ref=0, mirror=False)
    assert hand is not None and hand.n_views == n_cams
    err = np.linalg.norm(hand.points - pts, axis=1)
    assert err.mean() < 0.6                    # centimetres, from half-pixel noise


def test_more_cameras_are_more_accurate():
    errs = {}
    for n in (2, 4):
        e = []
        for s in range(20):
            rng = np.random.default_rng(s)
            models, pts = make_rig(n), fake_hand(rng)
            hand = fuse_hand(observe(models, pts, 1.0, rng), models, 0, mirror=False)
            e.append(np.linalg.norm(hand.points - pts, axis=1).mean())
        errs[n] = np.mean(e)
    assert errs[4] < errs[2]


def test_needs_two_views_and_ignores_unknown_cameras():
    rng = np.random.default_rng(1)
    models, pts = make_rig(3), fake_hand(rng)
    obs = observe(models, pts)
    assert fuse_hand({0: obs[0]}, models, 0) is None
    assert fuse_hand({0: obs[0], 9: obs[1]}, models, 0) is None        # camera 9 is not calibrated
    assert fuse_hand({1: obs[1], 2: obs[2]}, models, 0) is not None    # the reference camera is not required


def test_a_view_that_disagrees_is_dropped_when_others_agree():
    rng = np.random.default_rng(2)
    models, pts = make_rig(3), fake_hand(rng)
    obs = observe(models, pts, 0.3, rng)
    obs[2] = observe(models, fake_hand(np.random.default_rng(7)))[2]    # camera 2 saw a different hand position
    hand = fuse_hand(obs, models, 0, mirror=False, max_reproj_px=15)
    assert hand is not None and 2 not in hand.used
    assert np.linalg.norm(hand.points - pts, axis=1).mean() < 1.0


def test_reprojected_landmarks_match_reference_view_and_mirror():
    rng = np.random.default_rng(3)
    models, pts = make_rig(2), fake_hand(rng)
    obs = observe(models, pts)
    plain = fuse_hand(obs, models, 0, mirror=False)
    mirrored = fuse_hand(obs, models, 0, mirror=True)
    assert abs(plain.landmarks[5].x - obs[0][5].x) < 1e-3 and abs(plain.landmarks[5].y - obs[0][5].y) < 1e-3
    assert abs(mirrored.landmarks[5].x - (1 - obs[0][5].x)) < 1e-3


def synth_views(models, obj, n, rng):
    """The checkerboard shown to every camera in n random poses (only views that all cameras can see)."""
    views, attempts = [], 0
    while len(views) < n:
        attempts += 1
        assert attempts < 5000, "test setup: the board is never visible to every camera"
        rvec = rng.uniform(-0.45, 0.45, 3)
        R, _ = cv2.Rodrigues(rvec)
        centre = np.array([rng.uniform(-6, 6), rng.uniform(-4, 4), rng.uniform(55, 80)])
        X = (obj - obj.mean(0)) @ R.T + centre
        v = {}
        for i, m in models.items():
            px = m.project(X)
            if (px[:, 0] > 5).all() and (px[:, 0] < W - 5).all() and (px[:, 1] > 5).all() and (px[:, 1] < H - 5).all():
                v[i] = px
        if len(v) == len(models):
            views.append(v)
    return views


def test_rig_calibration_recovers_camera_poses():
    rng = np.random.default_rng(4)
    truth = make_rig(3)
    obj = board_points(9, 6, 2.5)
    views = synth_views(truth, obj, 25, rng)
    est = calibrate_rig(views, obj, {i: (W, H) for i in truth}, ref=0)
    for i in (1, 2):
        assert np.linalg.norm(est[i].t - truth[i].t) / np.linalg.norm(truth[i].t) < 0.03     # within 3 %
        ang = np.rad2deg(np.arccos(np.clip((np.trace(est[i].R @ truth[i].R.T) - 1) / 2, -1, 1)))
        assert ang < 1.0
    # and the estimated rig really triangulates
    pts = fake_hand(rng)
    hand = fuse_hand(observe(truth, pts), est, 0, mirror=False)
    assert np.linalg.norm(hand.points - pts, axis=1).mean() < 1.0


def test_calibration_needs_enough_views():
    rng = np.random.default_rng(5)
    truth = make_rig(2)
    obj = board_points(9, 6, 2.5)
    with pytest.raises(ValueError):
        calibrate_rig(synth_views(truth, obj, 4, rng), obj, {0: (W, H), 1: (W, H)}, ref=0)


def test_save_and_load_round_trip(tmp_path):
    models = make_rig(3)
    vol = {"min": [-10, -10, 30], "max": [10, 10, 70]}
    path = str(tmp_path / "cal.json")
    save_calibration(path, models, 0, {"cols": 9}, vol)
    loaded, ref, vol2, board = load_calibration(path)
    assert ref == 0 and vol2 == vol and board == {"cols": 9} and set(loaded) == {0, 1, 2}
    assert np.allclose(loaded[2].R, models[2].R) and np.allclose(loaded[2].t, models[2].t)


def test_rebase_when_reference_camera_is_unplugged():
    rng = np.random.default_rng(6)
    models, pts = make_rig(3), fake_hand(rng)
    obs = observe(models, pts)
    only = {i: models[i] for i in (1, 2)}
    new = rebase(only, new_ref=1)
    hand = fuse_hand({1: obs[1], 2: obs[2]}, new, ref=1, mirror=False)
    # points are now in camera 1's frame: compare distances, which do not depend on the frame
    d_true = np.linalg.norm(pts[0] - pts[1])
    assert abs(np.linalg.norm(hand.points[0] - hand.points[1]) - d_true) < 0.5
    vol = rebase_volume({"min": [-10, -10, 40], "max": [10, 10, 60]}, models, new_ref=1)
    centre_in_cam1 = models[1].R @ np.array([0, 0, 50.0]) + models[1].t
    assert volume_contains(vol, centre_in_cam1)


def test_volume_ignores_outliers_and_gates():
    rng = np.random.default_rng(8)
    pts = rng.normal([0, 0, 50], [4, 4, 4], (500, 3))
    pts[:5] = [200, 200, 200]                                   # a few wild outliers
    vol = volume_from_points(pts, margin_cm=5)
    assert volume_contains(vol, np.array([0, 0, 50.0]))
    assert not volume_contains(vol, np.array([0, 40, 50.0]))    # e.g. a hand resting low (out of the volume)
    assert vol["max"][0] < 40                                   # outliers did not blow the box up
    assert volume_contains(vol, np.array([0, 40, 50.0]), extra_cm=60)   # relaxed gate while holding something


def test_3d_pinch_is_not_fooled_by_foreshortening():
    from hexra.poses import RuleRecognizer

    pts = np.zeros((21, 3))
    pts[9] = [0, -5.0, 0]                       # palm length 5
    for pip, tip in ((6, 8), (10, 12), (14, 16), (18, 20)):
        pts[pip] = [0, -5.0, 0]
        pts[tip] = [0, -2.5, 0]                 # curled fingers
    pts[4] = [0.2, -2.5, 0]                     # thumb tip beside the index tip in the picture...
    pts[8] = [0.0, -2.5, 6.0]                   # ...but the index tip is really 6 cm closer to the camera
    assert RuleRecognizer(dims=2).predict_points(pts) == "click"       # a single camera is fooled
    assert RuleRecognizer(dims=3).predict_points(pts) != "click"       # stereo sees they are far apart


def test_detect_views_keeps_only_the_majority_hand():
    from hexra.stereo import detect_views, mirror_landmarks

    class T:
        def __init__(self, det):
            self.det = det

        def detect(self, frame, ts):
            return self.det

    lm = [type("L", (), {"x": 0.3, "y": 0.4, "z": 0.1})()] * 21
    trackers = {0: T((lm, "Right")), 1: T((lm, "Right")), 2: T((lm, "Left")), 3: T(None)}
    obs, label = detect_views(trackers, {0: "f", 1: "f", 2: "f", 3: "f"}, 1.0)
    assert set(obs) == {0, 1} and label == "Right"
    assert detect_views({0: T(None)}, {0: "f"}, 1.0) == ({}, None)
    assert abs(mirror_landmarks(lm)[0].x - 0.7) < 1e-9


def test_board_image_has_the_expected_inner_corners(tmp_path):
    import cv2

    from hexra.stereo import find_board
    from hexra.stereo_calibrate import make_board_png

    path = str(tmp_path / "b.png")
    make_board_png(path, 9, 6)
    corners = find_board(cv2.imread(path, cv2.IMREAD_GRAYSCALE), 9, 6)
    assert corners is not None and corners.shape == (54, 2)
