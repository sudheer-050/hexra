"""Window commands: thumbs-up (maximise), thumbs-down (minimise), L shape (close), and edge snapping."""
from types import SimpleNamespace as P

import numpy as np

from hexra.actions import NullMouse
from hexra.controller import Controller, ControllerConfig
from hexra.poses import RuleRecognizer
from hexra.windows import NullMover, snap_zone
from test_control import hand_points

# (landmarks 1..4 of the thumb) for a hand with the wrist at the origin and palm length 1; image y grows downwards
THUMB_UP = [(0.25, -0.10), (0.45, -0.30), (0.50, -0.72), (0.50, -1.15)]
THUMB_DOWN = [(0.20, -0.05), (0.35, 0.10), (0.40, 0.45), (0.40, 0.85)]
THUMB_SIDE = [(0.25, -0.10), (0.45, -0.30), (0.75, -0.34), (1.05, -0.36)]      # straight, out to the side
THUMB_DIAG = [(0.25, -0.10), (0.45, -0.30), (0.70, -0.55), (0.95, -0.80)]      # straight, 45 degrees up
THUMB_TUCKED = [(0.20, -0.10), (0.40, -0.30), (0.50, -0.45), (0.45, -0.55)]    # resting against the fist


def hand(thumb, index_up=False):
    pts = hand_points(index_up)
    for i, (x, y) in zip((1, 2, 3, 4), thumb):
        pts[i] = [x, y, 0.0]
    return pts


def rotated(pts, degrees):
    a = np.deg2rad(degrees)
    r = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    return (pts @ r.T).astype(np.float32)


# ---------------------------------------------------------------- the recogniser
def test_thumbs_up_thumbs_down_and_l_are_recognised():
    assert RuleRecognizer().predict_points(hand(THUMB_UP)) == "thumb_up"
    assert RuleRecognizer().predict_points(hand(THUMB_DOWN)) == "thumb_down"
    assert RuleRecognizer().predict_points(hand(THUMB_SIDE, index_up=True)) == "ell"


def test_an_ordinary_fist_is_never_a_command_however_the_thumb_rests():
    for thumb in (THUMB_TUCKED, THUMB_SIDE, THUMB_DIAG):
        assert RuleRecognizer().predict_points(hand(thumb)) == "fist", thumb


def test_pointing_is_not_an_l():
    assert RuleRecognizer().predict_points(hand(THUMB_DIAG, index_up=True)) == "point"       # thumb 45 degrees: not an L
    assert RuleRecognizer().predict_points(hand(THUMB_TUCKED, index_up=True)) == "point"


def test_a_thumb_out_of_a_held_fist_does_not_become_a_command():
    r = RuleRecognizer()
    assert r.predict_points(hand(THUMB_TUCKED)) == "fist"
    for _ in range(5):
        assert r.predict_points(hand(THUMB_UP)) == "fist"        # you are holding a fist: the thumb is ignored
    assert r.predict_points(hand(THUMB_UP, index_up=True)) != "thumb_up"
    r.predict_points(hand(THUMB_TUCKED, index_up=True))          # an open hand in between...
    assert r.predict_points(hand(THUMB_UP)) == "thumb_up"        # ...and now a thumbs-up counts


def test_thumbs_up_survives_a_little_tilt_but_not_a_lot():
    for deg in (-20, -10, 10, 20):
        assert RuleRecognizer().predict_points(rotated(hand(THUMB_UP), deg)) == "thumb_up", deg
    assert RuleRecognizer().predict_points(rotated(hand(THUMB_UP), 50)) == "fist"


def test_thumbs_up_does_not_flicker_once_held():
    r = RuleRecognizer()
    assert r.predict_points(hand(THUMB_UP)) == "thumb_up"
    assert r.predict_points(rotated(hand(THUMB_UP), 33)) == "thumb_up"           # looser while already held
    assert RuleRecognizer().predict_points(rotated(hand(THUMB_UP), 33)) == "fist"  # ...but it would not START there


# ---------------------------------------------------------------- the controller
def lm(x=0.5, y=0.5):
    pts = [P(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    pts[5] = P(x=x, y=y, z=0.0)
    return pts


def make(**kw):
    m, w = NullMouse(), NullMover()
    c = Controller(ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=2, **kw), m, w)
    return c, m, w


def feed(c, pose, seconds, t0, x=0.5, y=0.5, dt=0.033):
    t = t0
    while t < t0 + seconds:
        c.step(pose, lm(x, y), t)
        t += dt
    return t


def test_thumbs_up_fires_once_after_the_hold():
    c, m, w = make()
    t = feed(c, "palm", 0.3, 0.0)
    t = feed(c, "thumb_up", 0.4, t)
    assert w.commands == [] and 0.5 < c.cmd_progress < 1.0       # not yet; a ring is filling
    t = feed(c, "thumb_up", 0.3, t)
    assert w.commands == ["maximize"]
    feed(c, "thumb_up", 2.0, t)
    assert w.commands == ["maximize"]                            # holding on does not repeat it


def test_the_command_can_fire_again_only_after_leaving_the_pose():
    c, m, w = make()
    t = feed(c, "thumb_up", 0.7, 0.0)
    t = feed(c, "palm", 1.0, t)
    feed(c, "thumb_up", 0.7, t)
    assert w.commands == ["maximize", "maximize"]


def test_thumbs_down_minimises():
    c, m, w = make()
    feed(c, "thumb_down", 0.7, 0.0)
    assert w.commands == ["minimize"]


def test_close_needs_a_long_hold_and_shows_progress():
    c, m, w = make()
    t = feed(c, "ell", 1.0, 0.0)
    assert w.commands == [] and c.cmd_label == "close" and 0.5 < c.cmd_progress < 0.9
    t = feed(c, "ell", 0.7, t)
    assert w.commands == ["close"]
    assert c.cmd_progress == 0.0


def test_dropping_the_pose_cancels_a_close():
    c, m, w = make()
    t = feed(c, "ell", 1.2, 0.0)
    t = feed(c, "palm", 0.4, t)                                  # hand relaxes: cancelled
    assert c.cmd_progress == 0.0
    t = feed(c, "ell", 1.0, t)                                   # starting again needs the full hold
    assert w.commands == []
    feed(c, "ell", 0.8, t)
    assert w.commands == ["close"]


def test_a_brief_flicker_does_not_lose_the_progress():
    c, m, w = make()
    t = feed(c, "ell", 1.0, 0.0)
    c.step("palm", lm(), t)                                      # one misread frame
    t = feed(c, "ell", 0.6, t + 0.033)
    assert w.commands == ["close"]


def test_a_different_command_pose_restarts_the_count():
    c, m, w = make()
    t = feed(c, "ell", 1.2, 0.0)
    feed(c, "thumb_down", 0.3, t)                                # switched to thumbs-down: its own 0.5 s hold
    assert w.commands == []
    assert c.cmd_label == "minimise"


def test_the_cursor_does_not_move_while_a_command_pose_is_held():
    c, m, w = make()
    feed(c, "palm", 0.3, 0.0, x=0.2, y=0.2)
    before = m.position
    feed(c, "thumb_up", 0.6, 0.4, x=0.8, y=0.8)                  # the hand drifts, the cursor stays on the window
    assert m.position == before
    assert not m.is_down and m.right_clicks == 0


def test_no_command_fires_while_a_window_is_held_with_a_fist():
    c, m, w = make()
    t = feed(c, "fist", 0.4, 0.0)
    assert c.holding and w.grabbed
    feed(c, "thumb_up", 0.25, t)
    assert w.commands == []


def test_a_fist_cannot_grab_right_after_a_command():
    c, m, w = make()
    t = feed(c, "thumb_up", 0.7, 0.0)
    assert w.commands == ["maximize"]
    w.grabbed = None
    t = feed(c, "fist", 0.5, t)                                  # a hand relaxing out of the thumbs-up
    assert not w.grabbed
    feed(c, "fist", 0.8, t + 0.5)
    assert w.grabbed                                             # a deliberate fist a moment later still works


def test_commands_do_nothing_when_not_engaged():
    c, m, w = make()
    t = 0.0
    while t < 2.0:
        c.step("ell", lm(), t, engaged=False)
        t += 0.033
    assert w.commands == []


def test_remapping_a_command_pose_in_the_config_works():
    c, m, w = make(actions={"thumb_up": "minimize"})
    feed(c, "thumb_up", 0.7, 0.0)
    assert w.commands == ["minimize"]


# ---------------------------------------------------------------- edge snapping
def drag_and_release(c, x, y, release_pose="palm"):
    t = feed(c, "fist", 0.4, 0.0, x=0.5, y=0.5)
    t = feed(c, "fist", 0.3, t, x=x, y=y)
    return feed(c, release_pose, 0.5, t, x=x, y=y)


def test_snap_zone_geometry():
    r = (0, 0, 1000, 1000)
    assert snap_zone(5, 500, r, 30) == "left" and snap_zone(990, 500, r, 30) == "right"
    assert snap_zone(500, 5, r, 30) == "top" and snap_zone(500, 500, r, 30) is None
    assert snap_zone(5, 5, r, 30) == "left" and snap_zone(995, 5, r, 30) == "right"     # a corner is a side, never maximise
    assert snap_zone(1010, 500, (1000, 0, 1000, 1000), 30) == "left"                    # a second screen on the right


def test_dragging_to_the_left_edge_and_letting_go_snaps_left():
    c, m, w = make()
    drag_and_release(c, 0.005, 0.5)
    assert w.commands == ["snap:left"]


def test_right_edge_snaps_right_and_top_edge_maximises():
    c, m, w = make()
    drag_and_release(c, 0.995, 0.5)
    assert w.commands == ["snap:right"]
    c2, m2, w2 = make()
    drag_and_release(c2, 0.5, 0.004)
    assert w2.commands == ["snap:maximize"]


def test_letting_go_in_the_middle_does_not_snap():
    c, m, w = make()
    drag_and_release(c, 0.5, 0.5)
    assert w.commands == []


def test_a_live_hint_shows_while_in_the_zone():
    c, m, w = make()
    t = feed(c, "fist", 0.4, 0.0)
    feed(c, "fist", 0.3, t, x=0.005, y=0.5)
    assert c.hint == "release to snap left"
    t2 = feed(c, "fist", 0.3, t + 0.3, x=0.5, y=0.5)
    assert c.hint == ""


def test_losing_the_hand_at_an_edge_does_not_snap():
    c, m, w = make()
    t = feed(c, "fist", 0.4, 0.0)
    t = feed(c, "fist", 0.3, t, x=0.005, y=0.5)
    c.step(None, None, t + 1.0)                                  # tracking lost: the window is dropped, not snapped
    assert w.commands == []


def test_snapping_can_be_switched_off():
    c, m, w = make(snap_edges=False)
    drag_and_release(c, 0.005, 0.5)
    assert w.commands == [] and c.hint == ""


def test_snap_uses_the_screen_under_the_cursor_not_the_whole_desktop():
    c, m, w = make()
    w.monitor = (500, 0, 500, 1000)                              # the cursor is on a screen that starts at x=500
    drag_and_release(c, 0.52, 0.5)                               # 520 px: inside THAT screen's left edge zone
    assert w.commands == ["snap:left"]
