"""Relative (mouse-like) cursor mode: the cursor moves by how far the hand moves, with acceleration."""
from types import SimpleNamespace as P

import numpy as np

from hexra.actions import NullMouse
from hexra.controller import Controller, ControllerConfig
from hexra.windows import NullMover

FPS = 30


def lm(x=0.5, y=0.5):
    pts = [P(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    pts[5] = P(x=x, y=y, z=0.0)
    return pts


def make(start=(500.0, 500.0), **kw):
    m = NullMouse()
    m.position = start
    cfg = ControllerConfig(screen_w=1920, screen_h=1080, region=(0.2, 0.15, 0.8, 0.7), hold_frames=2,
                           cursor_mode="relative", **kw)
    return Controller(cfg, m, NullMover()), m


def move(c, pose, x0, x1, seconds, y=0.4, t0=0.0, settle=3):
    """Hand glides from x0 to x1 over `seconds` (after a few still frames), returns the end time."""
    n = max(int(seconds * FPS), 1)
    t = t0
    for _ in range(settle):
        c.step(pose, lm(x0, y), t)
        t += 1 / FPS
    for i in range(1, n + 1):
        c.step(pose, lm(x0 + (x1 - x0) * i / n, y), t)
        t += 1 / FPS
    for _ in range(settle):
        c.step(pose, lm(x1, y), t)
        t += 1 / FPS
    return t


def test_starts_from_the_real_cursor_and_does_not_jump():
    c, m = make(start=(500.0, 500.0))
    for i in range(10):
        c.step("palm", lm(0.3, 0.2), i / FPS)       # hand parked far from "centre": must not matter
    assert abs(m.position[0] - 500) < 2 and abs(m.position[1] - 500) < 2


def test_same_hand_distance_goes_farther_when_moved_fast():
    slow, ms = make()
    fast, mf = make()
    move(slow, "palm", 0.35, 0.45, 3.0)             # 0.1 of the picture in 3 s (slow, careful)
    move(fast, "palm", 0.35, 0.45, 0.12)            # the same 0.1 in 0.12 s (a flick)
    dx_slow, dx_fast = ms.position[0] - 500, mf.position[0] - 500
    assert 0 < dx_slow < 0.1 * (1920 / 0.6)         # careful move: finer than a 1:1 copy of the hand
    assert dx_fast > 2.5 * dx_slow                  # flick: acceleration carries the cursor much farther


def test_neutral_pose_lifts_the_mouse_without_a_jump():
    c, m = make()
    t = move(c, "palm", 0.3, 0.4, 0.5)
    before = m.position
    t = move(c, "point", 0.4, 0.7, 0.5, t0=t)       # index finger = neutral: hand travels, cursor must stay
    assert abs(m.position[0] - before[0]) < 1 and abs(m.position[1] - before[1]) < 1   # (filter settling only)
    for i in range(6):                              # open palm again at the new spot: no jump on re-entry
        c.step("palm", lm(0.7, 0.4), t + i / FPS)
    assert abs(m.position[0] - before[0]) < 3 and abs(m.position[1] - before[1]) < 3


def test_pinch_clicks_where_the_cursor_is_not_where_the_hand_is():
    c, m = make(start=(800.0, 400.0))
    for i in range(5):
        c.step("palm", lm(0.35, 0.3), i / FPS)
    for i in range(5):
        c.step("click", lm(0.35, 0.3), (5 + i) / FPS)
    assert m.is_down                                    # (absolute mode would have jumped to about (480, 294) first)
    assert abs(m.position[0] - 800) < 5 and abs(m.position[1] - 400) < 5


def test_a_tracking_glitch_does_not_fling_the_cursor():
    c, m = make(start=(800.0, 400.0))
    for i in range(6):
        c.step("palm", lm(0.35, 0.3), i / FPS)
    c.step("palm", lm(0.75, 0.6), 6 / FPS)               # tracker snaps to a far-away spot for one frame
    c.step("palm", lm(0.35, 0.3), 7 / FPS)
    for i in range(8, 14):
        c.step("palm", lm(0.35, 0.3), i / FPS)
    assert abs(m.position[0] - 800) < 40 and abs(m.position[1] - 400) < 40


def test_cursor_stays_on_screen():
    c, m = make(start=(1800.0, 500.0))
    move(c, "palm", 0.2, 0.8, 0.2)
    assert m.position[0] == 1919.0
    move(c, "palm", 0.8, 0.2, 0.1, t0=10)
    move(c, "palm", 0.8, 0.2, 0.1, t0=20)
    assert m.position[0] >= 0.0


def test_tremor_barely_moves_the_cursor():
    c, m = make()
    rng = np.random.default_rng(0)
    xs = []
    for i in range(120):
        c.step("palm", lm(0.5 + rng.normal(0, 0.003), 0.4 + rng.normal(0, 0.003)), i / FPS)
        if i > 30:
            xs.append(m.position[0])
    assert np.ptp(xs) < 25 and abs(np.mean(xs) - 500) < 25     # no steady drift either


def test_dragging_a_window_moves_it_by_the_cursor_delta():
    c, m = make(start=(600.0, 400.0))
    for i in range(4):
        c.step("palm", lm(0.4, 0.4), i / FPS)
    move(c, "fist", 0.4, 0.5, 0.3, t0=0.2)
    assert c.windows.grabbed is True or c.windows.position is not None
    dx = m.position[0] - 600
    assert dx > 20
    assert abs(c.windows.position[0] - dx) < 2        # the window travelled exactly as far as the cursor


def test_absolute_mode_is_unchanged():
    m = NullMouse()
    cfg = ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=2)
    c = Controller(cfg, m, NullMover())
    for i in range(6):
        c.step("palm", lm(0.25, 0.75), i / FPS)
    assert abs(m.position[0] - 250) < 5 and abs(m.position[1] - 750) < 5
