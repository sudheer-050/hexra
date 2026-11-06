"""Automatic hand-based calibration, tested on a simulated articulated hand and simulated cameras."""
import numpy as np
import pytest
from hand_sim import H, W, make_rig, simulate_samples

from gesture_control.autocal import (HandSampler, bone_cv, calibrate_from_hands, quality_problem, triangulate_frames)
from gesture_control.stereo import volume_contains


def rot_err_deg(a, b):
    return float(np.rad2deg(np.arccos(np.clip((np.trace(a @ b.T) - 1) / 2, -1, 1))))


def run(n_cams, baseline, noise, seed=10, frames=200):
    rng = np.random.default_rng(seed)
    truth_models = make_rig(n_cams, baseline)
    samples, truth = simulate_samples(truth_models, frames, rng, noise)
    models, report, volume = calibrate_from_hands(samples, {i: (W, H) for i in truth_models}, 0, 9.5)
    return truth_models, models, report, volume, samples, truth


def shape_error_cm(models, samples, truth):
    """Error of 3D landmark-to-landmark distances (independent of the coordinate frame)."""
    obs = {c: np.stack([s[c] for s in samples]) for c in models}
    est = triangulate_frames(obs, models)
    idx = np.random.default_rng(0).integers(0, 21, (60, 2))
    d_est = np.linalg.norm(est[:, idx[:, 0]] - est[:, idx[:, 1]], axis=2)
    d_true = np.linalg.norm(truth[:, idx[:, 0]] - truth[:, idx[:, 1]], axis=2)
    return float(np.mean(np.abs(d_est - d_true)))


def test_two_cameras_are_recovered_from_a_waving_hand():
    truth_m, models, report, volume, samples, truth = run(2, 18, 0.7)
    assert rot_err_deg(models[1].R, truth_m[1].R) < 2.0
    base_err = abs(np.linalg.norm(models[1].t) - np.linalg.norm(truth_m[1].t)) / np.linalg.norm(truth_m[1].t)
    assert base_err < 0.25                                   # distance between cameras: the weakest estimate
    assert shape_error_cm(models, samples, truth) < 0.5      # the 3D hand itself is accurate to a few mm
    assert report[1]["bone_cv"] < 0.15 and quality_problem(report) is None
    assert 0.6 <= report[1]["focal_scale"] <= 1.1            # focal length found without being told (true 0.85)


def test_wider_baseline_is_more_accurate():
    truth_m, models, *_ = run(2, 35, 1.0)
    assert rot_err_deg(models[1].R, truth_m[1].R) < 1.5
    assert abs(np.linalg.norm(models[1].t) - np.linalg.norm(truth_m[1].t)) / np.linalg.norm(truth_m[1].t) < 0.15


@pytest.mark.parametrize("n_cams", [3, 4])
def test_three_and_four_cameras(n_cams):
    truth_m, models, report, volume, samples, truth = run(n_cams, 16, 1.0)
    assert set(models) == set(range(n_cams))
    for i in range(1, n_cams):
        assert rot_err_deg(models[i].R, truth_m[i].R) < 8.0
    assert shape_error_cm(models, samples, truth) < 0.6
    assert quality_problem(report) is None


def test_air_zone_is_built_from_where_the_hand_went():
    truth_m, models, report, volume, samples, truth = run(2, 18, 0.7)
    assert volume is not None
    centre = np.mean([t[[0, 5, 9, 13, 17]].mean(axis=0) for t in truth], axis=0)   # true centre in camera 0's frame
    assert volume_contains(volume, centre)
    assert not volume_contains(volume, centre + np.array([0.0, 80.0, 0.0]))        # far below/above: outside


def test_too_few_matching_frames_is_a_clear_error():
    rng = np.random.default_rng(1)
    samples, _ = simulate_samples(make_rig(2), 10, rng)
    with pytest.raises(ValueError, match="only 10 frames"):
        calibrate_from_hands(samples, {0: (W, H), 1: (W, H)}, 0)


def test_garbage_matches_are_not_trusted():
    rng = np.random.default_rng(2)
    samples = [{0: rng.uniform(0, W, (21, 2)), 1: rng.uniform(0, W, (21, 2))} for _ in range(150)]
    try:
        _, report, _ = calibrate_from_hands(samples, {0: (W, H), 1: (W, H)}, 0)
    except ValueError:
        return                                               # refusing is fine
    assert quality_problem(report) is not None               # or it must be flagged as unreliable


def test_bone_lengths_are_a_good_quality_signal():
    rng = np.random.default_rng(3)
    _, truth = simulate_samples(make_rig(2), 100, rng, 0.0)
    assert bone_cv(truth) < 0.01                             # a real rigid-bone hand has constant bones
    assert bone_cv(truth + rng.normal(0, 1.5, truth.shape)) > 0.15


def test_sampler_skips_near_duplicate_frames_and_needs_two_cameras():
    s = HandSampler(min_move_px=8)
    a = np.zeros((21, 2))
    assert s.add({0: a, 1: a})
    assert not s.add({0: a + 1.0, 1: a})                     # barely moved
    assert s.add({0: a + 30.0, 1: a})
    assert s.add({1: a + 80, 2: a + 80})                     # any two cameras will do (camera 0 need not see it)
    assert not s.add({0: a + 99})                            # only one camera: not usable
    assert len(s.samples) == 3


def test_finish_picks_the_camera_that_saw_the_hand_most_and_explains_failures(tmp_path):
    from gesture_control.autocal import _finish

    rng = np.random.default_rng(11)
    models = make_rig(2, 18)
    samples, _ = simulate_samples(models, 120, rng, 0.7)
    swapped = [{1: s[1], 0: s[0]} for s in samples]
    ok, msg = _finish(swapped, {0: (W, H), 1: (W, H)}, str(tmp_path / "c.json"), 9.5)
    assert ok and "2 cameras calibrated" in msg
    ok, msg = _finish([], {0: (W, H), 1: (W, H)}, str(tmp_path / "d.json"), 9.5)
    assert not ok and "never seen by two cameras" in msg
    ok, msg = _finish(samples[:5], {0: (W, H), 1: (W, H)}, str(tmp_path / "e.json"), 9.5)
    assert not ok and "good frames" in msg and not (tmp_path / "e.json").exists()
