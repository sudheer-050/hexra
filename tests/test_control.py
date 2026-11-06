from types import SimpleNamespace as P

import numpy as np

from hexra.actions import NullMouse
from hexra.controller import Controller, ControllerConfig
from hexra.windows import NullMover
from hexra.poses import RuleRecognizer


def lm(x=0.5, y=0.5):
    pts = [P(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    pts[5] = P(x=x, y=y, z=0.0)
    return pts


def make(**kw):
    kw.setdefault("grab_move_px", 0.0)      # these tests describe taking hold of a window at once; test_commands.py covers the deferred grab
    m = NullMouse()
    c = Controller(ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=2, **kw), m, NullMover())
    return c, m


def run(c, pose, n, x=0.5, y=0.5, t0=0.0):
    for i in range(n):
        c.step(pose, lm(x, y), t0 + i * 0.033)


def test_palm_moves_cursor():
    c, m = make()
    run(c, "palm", 5, x=0.25, y=0.75)
    assert m.position is not None and abs(m.position[0] - 250) < 5 and abs(m.position[1] - 750) < 5


def test_cursor_move_starts_within_two_frames_after_neutral_pose():
    c, m = make()
    run(c, "point", 6)
    assert m.position is None
    c.step("palm", lm(0.3, 0.3), 1.0)
    c.step("palm", lm(0.3, 0.3), 1.033)
    assert m.position is not None           # 2 frames is enough to start moving


def test_click_still_needs_full_hold():
    m = NullMouse()
    c = Controller(ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=3), m, NullMover())
    run(c, "palm", 4)
    c.step("click", lm(), 1.0)
    c.step("click", lm(), 1.033)
    assert not m.is_down                     # only 2 of 3 frames
    c.step("click", lm(), 1.066)
    assert m.is_down                         # the third frame completes the hold


def test_point_is_neutral():
    c, m = make()
    run(c, "point", 10, x=0.25, y=0.75)
    assert m.position is None and not m.is_down and m.right_clicks == 0


def test_open_palm_moves_cursor_without_clicking():
    c, m = make()
    run(c, "palm", 12, x=0.4, y=0.6)
    assert abs(m.position[0] - 400) < 5 and abs(m.position[1] - 600) < 5
    assert not m.is_down and m.right_clicks == 0


def test_click_holds_and_releases():
    c, m = make()
    run(c, "palm", 4)
    run(c, "click", 4)
    assert m.is_down
    run(c, "palm", 8)          # letting go takes a sustained change (release_frames = 6)
    assert not m.is_down


def test_drag_survives_pose_flicker_and_short_dropout():
    m = NullMouse()
    c = Controller(ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=3), m, NullMover())
    run(c, "palm", 4)
    run(c, "click", 5)
    assert m.is_down
    for i in range(6):                       # pinch flickers to palm and back for 6 frames
        c.step("palm" if i % 2 else "click", lm(0.5 + 0.02 * i), 1.0 + i * 0.033)
    assert m.is_down
    for i in range(3):                       # 3 lost frames (about 0.1 s, e.g. motion blur)
        c.step(None, None, 1.2 + i * 0.033)
    assert m.is_down
    run(c, "click", 3, t0=1.4)
    assert m.is_down


def test_drag_ends_after_sustained_release_or_long_loss():
    m = NullMouse()
    c = Controller(ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=3), m, NullMover())
    run(c, "palm", 4)
    run(c, "click", 5)
    run(c, "palm", 10, t0=1.0)               # clearly opened the hand
    assert not m.is_down and "palm" in c.note
    run(c, "click", 5, t0=2.0)
    assert m.is_down
    c.step(None, None, 3.0)                  # lost for more than the grace period
    assert not m.is_down


def test_hand_lost_releases_button():
    c, m = make()
    run(c, "click", 4)
    assert m.is_down
    c.step(None, None, 1.0)
    assert not m.is_down


def test_right_click_once_per_entry():
    c, m = make()
    run(c, "right", 10)
    assert m.right_clicks == 1


def test_debounce_ignores_single_frame_glitch():
    c, m = make()
    run(c, "palm", 4)
    c.step("click", lm(), 0.5)   # one stray frame
    run(c, "palm", 3, t0=1.0)
    assert not m.is_down


def test_scroll_direction():
    c, m = make()
    run(c, "scroll", 3, y=0.6)
    for i in range(10):
        c.step("scroll", lm(y=0.6 - 0.02 * (i + 1)), 1.0 + i * 0.033)   # hand moves up
    assert m.scroll_total > 0


def test_shaky_hand_stays_put_but_real_moves_still_track():
    c, m = make()
    rng = np.random.default_rng(0)
    for i in range(60):   # hand "held still" with tremor of about 5 px
        c.step("palm", lm(0.5 + rng.normal(0, 0.003), 0.5 + rng.normal(0, 0.003)), i * 0.033)
    xs = []
    for i in range(30):
        c.step("palm", lm(0.5 + rng.normal(0, 0.003), 0.5 + rng.normal(0, 0.003)), 2.0 + i * 0.033)
        xs.append(m.position[0])
    assert max(xs) - min(xs) < 12          # jitter would be 20+ px without smoothing
    for i in range(40):                      # a deliberate move to x=0.8 must still arrive
        c.step("palm", lm(0.8, 0.5), 4.0 + i * 0.033)
    assert abs(m.position[0] - 800) < 30


def test_scroll_right_and_left_sideways():
    c, m = make()
    run(c, "scroll", 3, x=0.4)
    for i in range(10):
        c.step("scroll", lm(x=0.4 + 0.02 * (i + 1)), 1.0 + i * 0.033)   # hand moves right
    assert m.hscroll_total > 0 and m.scroll_total == 0
    before = m.hscroll_total
    for i in range(10):
        c.step("scroll", lm(x=0.6 - 0.02 * (i + 1)), 2.0 + i * 0.033)   # and back left
    assert m.hscroll_total < before and m.scroll_total == 0


def test_scroll_down_and_diagonal():
    c, m = make()
    run(c, "scroll", 3, x=0.4, y=0.4)
    for i in range(10):
        c.step("scroll", lm(x=0.4, y=0.4 + 0.02 * (i + 1)), 1.0 + i * 0.033)   # hand moves down
    assert m.scroll_total < 0 and m.hscroll_total == 0
    for i in range(10):
        c.step("scroll", lm(x=0.4 + 0.02 * (i + 1), y=0.6 - 0.02 * (i + 1)), 2.0 + i * 0.033)  # up and right
    assert m.hscroll_total > 0 and m.scroll_total > -10 and m.scroll_total != 0


def test_grabbed_window_survives_a_burst_of_misread_poses():
    c, _ = make()
    run(c, "fist", 4)
    assert c.windows.grabbed
    for i in range(8):                       # 8 wrong frames in a row (about 0.27 s) must not drop it
        c.step("palm" if i % 3 else "click", lm(), 1.0 + i * 0.033)
    assert c.windows.grabbed
    run(c, "fist", 3, t0=2.0)
    assert c.windows.grabbed


def test_fist_moves_window_with_hand():
    c, _ = make()
    run(c, "fist", 3, x=0.5, y=0.5)
    assert c.windows.grabbed
    start = c.windows.position
    run(c, "fist", 6, x=0.6, y=0.5, t0=1.0)   # hand moves right by 0.1 of the region = 100 px
    assert c.windows.position[0] > start[0] + 50


def test_fist_cursor_follows_hand_while_dragging_window():
    c, m = make()
    run(c, "fist", 3, x=0.5, y=0.5)
    run(c, "fist", 6, x=0.7, y=0.5, t0=1.0)
    assert m.position is not None and m.position[0] > 600


def test_open_palm_drops_window():
    c, _ = make()
    run(c, "fist", 4)
    run(c, "palm", 12, t0=1.0)
    assert c.windows.grabbed is None


def test_hand_lost_drops_window():
    c, _ = make()
    run(c, "fist", 4)
    c.step(None, None, 2.0)
    assert c.windows.grabbed is None


def test_ambiguous_hand_is_not_a_grab():
    r = RuleRecognizer()
    pts = hand_points(index_up=True, ring_up=True)  # odd finger combination
    assert r.predict_points(pts) == "palm"


def test_not_engaged_is_inert():
    c, m = make()
    for i in range(5):
        c.step("click", lm(), i * 0.03, engaged=False)
    assert not m.is_down and m.position is None


KNUCKLE = {"index": (-0.3, -1.0), "middle": (0.0, -1.0), "ring": (0.3, -1.0), "pinky": (0.55, -0.85)}
CHAIN = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20)}
BONES = {"index": (0.42, 0.24, 0.21), "middle": (0.46, 0.28, 0.22), "ring": (0.42, 0.27, 0.21), "pinky": (0.34, 0.19, 0.19)}


def put_finger(pts, name, extended, reach=None):
    """Four landmarks for a finger (palm length = 1, wrist at the origin): straight when extended, folded when curled."""
    ids, (kx, ky) = CHAIN[name], KNUCKLE[name]
    pts[ids[0]] = [kx, ky, 0]
    if extended:
        y = ky
        for k, length in enumerate(BONES[name]):
            y -= length
            pts[ids[k + 1]] = [kx, y, 0]
        if reach is not None:                                  # stretch the straight finger so the tip reaches `reach`
            for k in range(1, 4):
                pts[ids[k]] = [kx, ky + (-reach - ky) * k / 3, 0]
    else:
        pts[ids[1]] = [kx, ky - 0.15, 0]
        pts[ids[2]] = [kx, ky - 0.05, 0]
        pts[ids[3]] = [kx, ky + 0.07 if reach is None else -reach, 0]


def hand_points(index_up=False, middle_up=False, ring_up=False, pinky_up=False, pinch=None):
    pts = np.zeros((21, 3), np.float32)
    for name, up in (("index", index_up), ("middle", middle_up), ("ring", ring_up), ("pinky", pinky_up)):
        put_finger(pts, name, up)
    pts[4] = [1.0, -0.5, 0]
    pts[8, :2] = pts[8, :2] if pinch != "index" else pts[4, :2] + [0.05, 0]
    if pinch == "middle":
        pts[12, :2] = pts[4, :2] + [0.05, 0]
    return pts


def curl(tips):
    """A hand whose four fingertips are at the given distances (palm length = 1) from the wrist."""
    pts = np.zeros((21, 3), np.float32)
    for name, r in zip(("index", "middle", "ring", "pinky"), tips):
        put_finger(pts, name, extended=r >= 1.4, reach=r)
    pts[4] = [1.0, -0.6, 0]                   # thumb far from the index tip unless a test moves it
    return pts


def turned(pts, yaw_deg, pitch_deg):
    """The hand turned about its wrist and seen by an (orthographic) camera: distances shrink like a real turned hand."""
    a, b = np.deg2rad(yaw_deg), np.deg2rad(pitch_deg)
    ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    return (pts @ (rx @ ry).T).astype(np.float32)


def test_fist_is_found_by_reach_not_by_a_twitchy_tip_vs_joint_test():
    r = RuleRecognizer()
    # Real fists: tips about 0.7-1.3 palm-lengths from the wrist. The old test called a 1.2 reach "extended" -> palm.
    assert r.predict_points(curl([0.9, 1.0, 0.95, 0.9])) == "fist"
    assert RuleRecognizer().predict_points(curl([1.9, 2.0, 1.8, 1.6])) == "palm"
    # fingers only partly curled (about 60%) are NOT a fist any more: they would grab a window by accident
    assert RuleRecognizer().predict_points(curl([1.2, 1.3, 1.25, 1.1])) != "fist"


def test_a_fist_sticks_while_it_loosens_or_the_thumb_touches_the_index():
    r = RuleRecognizer()
    assert r.predict_points(curl([0.9, 0.9, 0.9, 0.9])) == "fist"
    loose = curl([1.3, 1.35, 1.3, 1.1])                      # fingers loosening (tilt, motion): not yet "clearly open"
    assert r.predict_points(loose) == "fist"
    assert RuleRecognizer().predict_points(loose) != "fist"  # ...but a hand that STARTS this loose is not a fist
    touching = curl([0.9, 0.9, 0.9, 0.9])
    touching[4] = [0.03, -1.0, 0.0]                          # thumb right against the index fingertip
    assert r.predict_points(touching) == "fist"              # NOT a click
    assert r.predict_points(curl([1.9, 1.9, 1.9, 1.7])) == "palm"   # a clearly open hand does release it


def test_a_fresh_pinch_is_still_a_click_and_a_loose_hand_does_not_start_a_fist():
    r = RuleRecognizer()
    pinch = curl([1.7, 1.7, 1.7, 1.5])
    pinch[4] = [0.0, -1.5, 0.0]
    pinch[8] = [0.02, -1.5, 0.0]                             # thumb tip meets index tip (tips near palm length 1.5)
    assert r.predict_points(pinch) == "click"
    assert RuleRecognizer().predict_points(curl([1.5, 1.6, 1.5, 1.3])) != "fist"   # a relaxed hand does not START a fist


def test_pinch_has_hysteresis():
    r = RuleRecognizer()
    pts = hand_points(index_up=True, middle_up=True, ring_up=True, pinky_up=True, pinch="index")
    assert r.predict_points(pts) == "click"
    pts[8, :2] = pts[4, :2] + [0.33, 0]      # fingers drift apart (hand tilting): 0.33 of palm size
    assert r.predict_points(pts) == "click"  # still held
    pts[8, :2] = pts[4, :2] + [0.7, 0]
    assert r.predict_points(pts) != "click"  # clearly open
    pts[8, :2] = pts[4, :2] + [0.33, 0]
    assert r.predict_points(pts) != "click"  # and 0.33 no longer STARTS a pinch


def test_rule_recognizer():
    r = RuleRecognizer()
    assert r.predict_points(hand_points()) == "fist"
    assert r.predict_points(hand_points(True, True, True, True)) == "palm"
    assert r.predict_points(hand_points(index_up=True)) == "point"
    assert r.predict_points(hand_points(True, True)) == "scroll"
    assert r.predict_points(hand_points(middle_up=True, ring_up=True, pinky_up=True, pinch="index")) == "click"
    assert r.predict_points(hand_points(True, True, True)) == "right"
    # a curled middle finger resting near the thumb (normal when pointing) must NOT read as right-click
    pts = hand_points(index_up=True)
    pts[4] = [0.03, -0.5, 0]          # thumb tip resting right against the curled middle fingertip
    assert r.predict_points(pts) == "point"


def test_an_open_palm_is_never_read_as_a_right_click_however_it_is_turned():
    """The bug: turning the hand shrank the pinky's apparent reach, so 4 open fingers became '3 fingers' (right click)."""
    open_hand = hand_points(True, True, True, True)
    for yaw in (-65, -45, -25, 0, 25, 45, 65):
        for pitch in (-60, -40, 0, 40, 60):
            pose = RuleRecognizer().predict_points(turned(open_hand, yaw, pitch))
            assert pose == "palm", f"open palm turned yaw={yaw} pitch={pitch} was read as {pose}"


def test_real_gestures_still_work_when_the_hand_is_a_little_turned():
    for yaw, pitch in ((0, 0), (15, 0), (-15, 10), (10, -15)):
        assert RuleRecognizer().predict_points(turned(hand_points(True, True, True), yaw, pitch)) == "right"
        assert RuleRecognizer().predict_points(turned(hand_points(True, True), yaw, pitch)) == "scroll"
        assert RuleRecognizer().predict_points(turned(hand_points(True), yaw, pitch)) == "point"
        assert RuleRecognizer().predict_points(turned(hand_points(), yaw, pitch)) == "fist"


def bent_finger(pts, name, target_s):
    """Bend a finger sideways (bisection) until its straightness, as the recogniser measures it, is `target_s`."""
    from hexra.poses import _straightness

    ids, (kx, ky) = CHAIN[name], KNUCKLE[name]
    chord = sum(BONES[name]) * 0.9

    def build(d):
        pts[ids[0]] = [kx, ky, 0]
        pts[ids[1]] = [kx + d, ky - chord * 0.35, 0]
        pts[ids[2]] = [kx - d, ky - chord * 0.7, 0]
        pts[ids[3]] = [kx, ky - chord, 0]
        return _straightness(pts, ids)

    lo, hi = 0.0, chord
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if build(mid) > target_s else (lo, mid)
    build((lo + hi) / 2)


def bent_scroll_hand(index_s, middle_s):
    """Index and middle fingers with the given straightness (the ring and pinky curled), palm length 1."""
    pts = hand_points(False, False, False, False)
    bent_finger(pts, "index", index_s)
    bent_finger(pts, "middle", middle_s)
    return pts


def test_scroll_survives_fingers_relaxing_a_little_but_a_fresh_relaxed_hand_is_not_scroll():
    r = RuleRecognizer()
    assert r.predict_points(hand_points(True, True)) == "scroll"             # a firm two-finger scroll
    relaxed = bent_scroll_hand(0.82, 0.82)                                   # fingers a little bent (tired hand)
    assert r.predict_points(relaxed) == "scroll"                             # still scrolling
    assert RuleRecognizer().predict_points(relaxed) != "scroll"              # but it would not START a scroll


def test_two_scrolling_fingers_curling_does_not_become_a_fist_until_really_closed():
    for s in (0.8, 0.6, 0.45):                                               # progressively more curled
        pose = RuleRecognizer().predict_points(bent_scroll_hand(s, s))
        assert pose != "fist", f"fingers at straightness {s} were read as a fist"


def test_window_grab_needs_the_longer_hold():
    m = NullMouse()
    cfg = ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=2, grab_frames=5, grab_move_px=0)
    c = Controller(cfg, m, NullMover())
    for i in range(4):
        c.step("fist", lm(), i / 30)
    assert not c.windows.grabbed                                             # 4 frames: not yet
    c.step("fist", lm(), 4 / 30)
    assert c.windows.grabbed                                                 # 5th frame: grabbed
