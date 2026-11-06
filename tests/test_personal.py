"""Personal calibration: the hand features, the nearest-example recogniser, its cross-validation and the first-run state machine."""
import numpy as np
import pytest

from hexra.calibration import STEPS, Calibrator
from hexra.handfeat import NAMES, hand_features
from hexra.personal import PersonalModel, PersonalRecognizer, build, cross_validate
from hexra.poses import RuleRecognizer
from test_commands import THUMB_DOWN, THUMB_TUCKED, THUMB_UP, hand
from test_control import hand_points, turned


def poses():
    ok_sign = hand_points(middle_up=True, ring_up=True, pinky_up=True, pinch="index")
    return {"palm": hand_points(True, True, True, True), "fist": hand(THUMB_TUCKED), "thumb_up": hand(THUMB_UP), "thumb_down": hand(THUMB_DOWN),
            "click": ok_sign, "point": hand_points(index_up=True)}


def examples(pts, n=150, seed=0, turn=20.0, noise=0.01):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        h = turned(pts, rng.uniform(-turn, turn), rng.uniform(-turn, turn)) + rng.normal(0, noise, pts.shape).astype(np.float32)
        out.append(hand_features(h))
    return np.vstack(out)


def samples(seed=0):
    return {name: examples(p, seed=seed + i) for i, (name, p) in enumerate(poses().items())}


# ---------------------------------------------------------------- features
def test_features_are_a_fixed_length_ratio_vector_independent_of_size_and_position():
    p = hand(THUMB_UP)
    f = hand_features(p)
    assert f.shape == (len(NAMES),) and np.all(np.isfinite(f))
    assert np.allclose(f, hand_features(p * 3.0 + 5.0), atol=1e-4)           # scaling and shifting the hand changes nothing


def test_a_tucked_thumb_and_a_raised_thumb_have_clearly_different_features():
    a, b = hand_features(hand(THUMB_TUCKED)), hand_features(hand(THUMB_UP))
    i = NAMES.index("thumb_len")
    assert b[i] > a[i] + 0.3


# ---------------------------------------------------------------- the model
def test_each_pose_is_recognised_from_its_own_examples_even_when_the_hand_is_turned():
    res = cross_validate(samples())
    assert all(a >= 0.9 for a in res["accuracy"].values()), res["accuracy"]
    assert not res["mixups"]


def test_the_model_separates_new_examples_it_has_not_seen():
    model, report = build(samples(seed=0))
    fresh = {n: examples(p, n=40, seed=500 + i) for i, (n, p) in enumerate(poses().items())}
    for name, rows in fresh.items():
        right = sum(model.predict_vector(r)[0] == name for r in rows)
        assert right / len(rows) >= 0.9, (name, right)
    assert report["poses"] and report["examples"]["fist"] == 150


def test_a_fist_with_the_thumb_touching_the_index_is_a_fist_for_this_hand_though_the_rules_call_it_a_click():
    touching = hand(THUMB_TUCKED)
    touching[4, :2] = touching[8, :2] + [0.04, 0.0]                           # thumb tip on the index tip: the rules see a pinch
    feats = touching.reshape(-1)
    assert RuleRecognizer().predict_features(feats) == "click"
    data = samples()
    data["fist"] = np.vstack([data["fist"], examples(touching, seed=77)])      # YOUR fist looks like this, and you showed it in calibration
    model, _ = build(data)
    rec = PersonalRecognizer(model)
    out = [rec.predict_features(turned(touching, 5, 5).reshape(-1)) for _ in range(5)]
    assert out[-1] == "fist"


def test_two_poses_that_look_alike_are_reported_rather_than_hidden():
    data = samples()
    data["thumb_up_again"] = examples(hand(THUMB_UP), seed=900)               # the same pose recorded under two names
    res = cross_validate(data)
    assert res["mixups"] and {m["pose"] for m in res["mixups"]} & {"thumb_up", "thumb_up_again"}


def test_something_unfamiliar_falls_back_to_the_rules_and_never_crashes():
    model, _ = build(samples())
    rec = PersonalRecognizer(model)
    weird = np.random.default_rng(1).normal(0, 3.0, (21, 3)).astype(np.float32)
    assert isinstance(rec.predict_features(weird.reshape(-1)), str)


def test_the_model_survives_saving_and_loading(tmp_path):
    model, _ = build(samples())
    f = tmp_path / "calibration.npz"
    model.save(f)
    again = PersonalModel.load(f)
    row = examples(hand(THUMB_UP), n=1, seed=3)[0]
    assert again.predict_vector(row)[0] == model.predict_vector(row)[0] == "thumb_up"
    assert again.max_dist == pytest.approx(model.max_dist)


def test_smoothing_ignores_a_single_wrong_frame():
    model, _ = build(samples())
    rec = PersonalRecognizer(model, smooth=3)
    up, down = hand(THUMB_UP).reshape(-1), hand(THUMB_DOWN).reshape(-1)
    seq = [rec.predict_features(x) for x in (up, up, down, up)]
    assert seq[-1] == "thumb_up" and seq[2] == "thumb_up"                      # the one odd frame did not flip the pose


# ---------------------------------------------------------------- the first-run walk-through
def run(cal, hand_pts, seconds, t0, dt=0.033, seen=True):
    t = t0
    while t < t0 + seconds and not cal.done:
        cal.update(hand_pts.reshape(-1) if seen else None, t)
        t += dt
    return t


def test_it_asks_for_each_pose_in_turn_with_a_get_ready_then_a_hold():
    cal = Calibrator(ready_s=1.0, hold_s=2.0, min_frames=20)
    cal.update(hand(THUMB_TUCKED).reshape(-1), 0.0)
    snap = cal.snapshot()
    assert snap["phase"] == "ready" and snap["title"] == STEPS[0]["title"] and snap["step"] == 0 and snap["total"] == len(STEPS)
    cal.update(hand(THUMB_TUCKED).reshape(-1), 1.1)
    assert cal.snapshot()["phase"] == "hold"


def test_a_complete_run_records_every_pose_and_finishes():
    cal = Calibrator(ready_s=0.5, hold_s=1.5, min_frames=20)
    t = 0.0
    for step in STEPS:
        pts = poses().get(step["pose"])
        pts = hand(THUMB_TUCKED) if pts is None else pts
        t = run(cal, pts, 2.1, t)
    assert cal.done and set(cal.samples) == {s["pose"] for s in STEPS} and not cal.skipped
    assert all(v.shape[1] == len(NAMES) and len(v) >= 20 for v in cal.samples.values())


def test_a_pose_where_no_hand_was_seen_is_asked_again_then_skipped():
    cal = Calibrator(steps=STEPS[:2], ready_s=0.3, hold_s=0.6, min_frames=10, retries=2, skip_s=0.0)
    t = 0.0
    while t < 6 and cal.snapshot()["pose"] == "palm":
        cal.update(None, t)                                   # nobody there
        t += 0.033
    assert "palm" in cal.skipped and not cal.done            # skipped after two more tries, and it moved on to the fist
    assert cal.snapshot()["pose"] == "fist"
    run(cal, hand(THUMB_TUCKED), 3.0, t)
    assert cal.done and set(cal.samples) == {"fist"}


def test_the_first_retry_says_why():
    cal = Calibrator(steps=STEPS[:1], ready_s=0.2, hold_s=0.4, min_frames=10, skip_s=0.0)
    t = 0.0
    while t < 0.8:
        cal.update(None, t)
        t += 0.033
    assert cal.snapshot()["phase"] == "ready" and "try that one again" in cal.snapshot()["message"]


def test_the_first_moments_of_a_hold_and_stray_frames_are_not_recorded():
    cal = Calibrator(steps=STEPS[:1], ready_s=0.2, hold_s=2.0, min_frames=20, skip_s=0.7, trim=0.1)
    t = 0.0
    fist, up = hand(THUMB_TUCKED), hand(THUMB_UP)
    while t < 0.3:                                                         # get ready
        cal.update(fist.reshape(-1), t); t += 0.033
    while t < 1.0:                                                         # still getting into the pose: shows a different one
        cal.update(up.reshape(-1), t); t += 0.033
    while t < 2.6 and not cal.done:
        cal.update(fist.reshape(-1), t); t += 0.033
    rows = cal.samples["palm"]
    assert len(rows) >= 20
    assert np.all(np.abs(rows[:, NAMES.index("thumb_len")] - hand_features(fist)[NAMES.index("thumb_len")]) < 0.05)    # only the real pose was kept
