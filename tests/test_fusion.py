"""Two-camera fusion: learns how the views line up, averages the cursor point, picks the better view for pose, fails over."""
from types import SimpleNamespace

import numpy as np

from hexra.fusion import KNUCKLES, AffineMap, Fuser, Observation, control_point

# camera 2 sees the same hand through a different angle: a rotation + scale + shift of camera 1's picture
M_TRUE = np.array([[0.9, -0.25, 0.20], [0.30, 0.85, 0.05]])


def to_cam2(p):
    return M_TRUE[:, :2] @ np.asarray(p) + M_TRUE[:, 2]


def make_lm(centre, offset=None):
    """21 landmarks; the four knuckles sit symmetrically around `centre`, the rest are spread so the shape is a real hand."""
    c = np.asarray(centre, float)
    pts = []
    for i in range(21):
        a = i * 0.7
        d = np.array([0.02 * np.cos(a), 0.02 * np.sin(a)]) * (1 + i / 10)
        pts.append(c + d)
    pts = np.array(pts)
    pts[list(KNUCKLES)] = c + np.array([[-0.03, -0.01], [-0.01, 0.01], [0.01, 0.01], [0.03, -0.01]])      # offsets average to zero
    if offset is not None:
        pts += offset
    return [SimpleNamespace(x=float(x), y=float(y), z=0.0) for x, y in pts]


def truth(i):
    return np.array([0.5 + 0.28 * np.sin(i * 0.05), 0.5 + 0.22 * np.cos(i * 0.037)])


def obs_pair(i, rng, sigma=0.003, score0=0.95, score1=0.95, t0=0.0):
    t = t0 + i / 30
    p = truth(i)
    o0 = Observation(t, make_lm(p + rng.normal(0, sigma, 2)), "Right", score0)
    q = to_cam2(p) + rng.normal(0, sigma, 2)
    o1 = Observation(t + 0.008, make_lm(q, None), "Right", score1)
    return o0, o1, t + 0.008


def warm_up(f, rng, n=260):
    out = None
    for i in range(n):
        o0, o1, t = obs_pair(i, rng)
        out = f.update(o0, o1, t)
    return out


# ---------------------------------------------------------------- learning the map
def test_the_map_between_the_views_is_learned_from_use_without_any_setup():
    rng = np.random.default_rng(1)
    f = Fuser()
    out = warm_up(f, rng)
    assert f.ready and out.mode == "fused"
    p = np.array([0.4, 0.55])
    assert np.linalg.norm(f.map.apply(to_cam2(p)) - p) < 0.01


def test_before_enough_motion_has_been_seen_it_says_it_is_learning_and_uses_the_better_camera():
    rng = np.random.default_rng(2)
    f = Fuser()
    out = None
    for i in range(10):
        o0, o1, t = obs_pair(i, rng)
        out = f.update(o0, o1, t)
    assert out.mode.startswith("learning") and not f.ready
    assert np.linalg.norm(np.array(out.point) - truth(9)) < 0.02          # still follows the hand (camera 1's frame)


def test_a_hand_that_barely_moves_does_not_count_as_learned():
    rng = np.random.default_rng(3)
    f = Fuser()
    for i in range(300):
        t = i / 30
        p = np.array([0.5, 0.5]) + rng.normal(0, 0.001, 2)
        f.update(Observation(t, make_lm(p), "Right"), Observation(t + 0.005, make_lm(to_cam2(p)), "Right"), t + 0.005)
    assert not f.ready                                                     # no spread: the map would be ill-conditioned


def test_the_affine_map_recovers_a_known_transform():
    rng = np.random.default_rng(4)
    m = AffineMap()
    for i in range(200):
        p = truth(i)
        m.add(p + rng.normal(0, 0.002, 2), to_cam2(p) + rng.normal(0, 0.002, 2))
    m.fit()
    assert m.rms() < 0.01 and m.spread > 0.1


# ---------------------------------------------------------------- precision
def test_the_fused_point_is_steadier_than_either_camera_alone():
    rng = np.random.default_rng(5)
    f = Fuser()
    warm_up(f, rng)
    fused_err, single_err = [], []
    for i in range(260, 760):
        o0, o1, t = obs_pair(i, rng, sigma=0.004)
        out = f.update(o0, o1, t)
        assert out.mode == "fused"
        fused_err.append(np.linalg.norm(np.array(out.point) - truth(i)))
        single_err.append(np.linalg.norm(control_point(o0.lm) - truth(i)))
    rms = lambda e: float(np.sqrt(np.mean(np.square(e))))
    assert rms(fused_err) < 0.85 * rms(single_err)                         # independent noise partly cancels (ideal ratio 0.71)


# ---------------------------------------------------------------- failover, no jumps
def test_when_one_camera_loses_the_hand_the_other_carries_on_without_a_jump():
    rng = np.random.default_rng(6)
    f = Fuser()
    warm_up(f, rng)
    prev = None
    for i in range(260, 330):
        o0, o1, t = obs_pair(i, rng)
        out = f.update(None if i >= 300 else o0, o1, t)
        if i >= 300:
            assert out.mode == "camera 2 only"
        if prev is not None:
            assert np.linalg.norm(np.array(out.point) - prev) < 0.03, i     # a normal hand step, never a jump at the switch
        prev = np.array(out.point)


def test_camera_2_alone_before_it_has_ever_been_matched_still_does_not_jump():
    rng = np.random.default_rng(7)
    f = Fuser()
    prev = None
    for i in range(40):
        o0, o1, t = obs_pair(i, rng)
        out = f.update(o0 if i < 20 else None, o1, t)
        if prev is not None:
            assert np.linalg.norm(np.array(out.point) - prev) < 0.03, i
        prev = np.array(out.point)
    assert out.mode == "camera 2 only"


def test_camera_1_alone_and_nothing_at_all():
    rng = np.random.default_rng(8)
    f = Fuser()
    o0, _, t = obs_pair(0, rng)
    assert f.update(o0, None, t).mode == "camera 1 only"
    assert f.update(None, None, t + 0.03) is None


def test_an_old_observation_counts_as_not_seen():
    rng = np.random.default_rng(9)
    f = Fuser(max_age_s=0.1)
    o0, o1, t = obs_pair(0, rng)
    assert f.update(o0, o1, t + 0.5) is None


# ---------------------------------------------------------------- the pose comes from the better view
def test_the_pose_camera_changes_only_when_the_other_view_is_clearly_better_for_a_while():
    rng = np.random.default_rng(10)
    f = Fuser(switch_hold_s=0.4)
    warm_up(f, rng)
    assert f.best == 0
    for i in range(260, 270):                                              # camera 2 slightly better for a third of a second: no switch
        o0, o1, t = obs_pair(i, rng, score0=0.80, score1=0.95)
        out = f.update(o0, o1, t)
    assert f.best == 0 and out.best == 0
    for i in range(270, 300):                                              # clearly and persistently better: switch
        o0, o1, t = obs_pair(i, rng, score0=0.60, score1=0.97)
        out = f.update(o0, o1, t)
    assert f.best == 1 and out.best == 1


def test_finger_shape_is_not_blended_and_the_cursor_point_is_the_fused_one():
    rng = np.random.default_rng(11)
    f = Fuser()
    warm_up(f, rng)
    o0, o1, t = obs_pair(300, rng)
    out = f.update(o0, o1, t)
    assert out.raw is o0.lm                                                # pose features come straight from the best camera
    assert np.allclose(control_point(out.lm), out.point, atol=1e-9)        # but the controller's knuckle average is the fused point


# ---------------------------------------------------------------- the views stop agreeing
def test_if_a_camera_is_bumped_the_fuser_stops_trusting_the_old_map_and_relearns():
    rng = np.random.default_rng(12)
    f = Fuser()
    warm_up(f, rng)
    modes = []
    for i in range(260, 330):
        o0, o1, t = obs_pair(i, rng)
        o1 = Observation(o1.t, make_lm(to_cam2(truth(i)) + np.array([0.25, -0.2])), "Right", 0.95)    # camera 2 moved
        out = f.update(o0, o1, t)
        modes.append(out.mode)
        assert np.linalg.norm(np.array(out.point) - truth(i)) < 0.05      # never follows the wrong camera
    assert modes[0] != "fused" or modes[1] != "fused"
    assert any(m.startswith("learning") for m in modes)


# ---------------------------------------------------------------- what "a better view" means
def test_a_hand_cut_off_by_the_edge_or_small_in_the_picture_is_a_worse_view():
    from hexra.fusion import quality
    good = Observation(0, make_lm([0.5, 0.5]), "Right", 0.9)
    cut = Observation(0, make_lm([0.99, 0.5]), "Right", 0.9)               # half the hand is outside the picture
    small = Observation(0, [SimpleNamespace(x=0.5 + (p.x - 0.5) * 0.3, y=0.5 + (p.y - 0.5) * 0.3, z=0) for p in make_lm([0.5, 0.5])], "Right", 0.9)
    assert quality(cut) < quality(good) and quality(small) < quality(good)
    assert quality(Observation(0, make_lm([0.5, 0.5]), "Right", 0.5)) < quality(good)


def test_the_camera_that_sees_the_whole_hand_takes_over_the_pose_when_the_other_loses_part_of_it():
    rng = np.random.default_rng(13)
    f = Fuser(switch_hold_s=0.3)
    warm_up(f, rng)
    for i in range(260, 300):
        o0, o1, t = obs_pair(i, rng)
        o0 = Observation(o0.t, make_lm([0.995, truth(i)[1]]), "Right", 0.95)      # camera 1 only sees half the hand
        out = f.update(o0, o1, t)
    assert out.best == 1 and out.raw is o1.lm


def test_the_better_view_counts_for_more_in_the_fused_cursor_point():
    rng = np.random.default_rng(14)
    f = Fuser()
    warm_up(f, rng)
    p = truth(400)
    t = 400 / 30
    o0 = Observation(t, make_lm(p + np.array([0.02, 0.0])), "Right", 0.95)          # camera 1 is off by 0.02 ...
    o1 = Observation(t + 0.004, make_lm(to_cam2(p)), "Right", 0.95)                 # ... camera 2 is exact
    out_equal = np.array(f.update(o0, o1, t + 0.004).point)
    f2 = Fuser()
    warm_up(f2, np.random.default_rng(14))
    o1w = Observation(t + 0.004, make_lm(to_cam2(p)), "Right", 0.95)
    o0w = Observation(t, make_lm(p + np.array([0.02, 0.0])), "Right", 0.55)         # camera 1 is a poorer view this time
    out_weighted = np.array(f2.update(o0w, o1w, t + 0.004).point)
    assert np.linalg.norm(out_weighted - p) < np.linalg.norm(out_equal - p)         # leaning on the good camera is closer to the truth
