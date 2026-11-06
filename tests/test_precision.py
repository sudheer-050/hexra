"""Precision features: the knuckle-average cursor point and click placement that undoes pinch drift."""
from types import SimpleNamespace as P

import numpy as np

from hexra.actions import NullMouse
from hexra.controller import Controller, ControllerConfig
from hexra.windows import NullMover

FPS = 30


def hand(index=(0.4, 0.4), others=(0.4, 0.4)):
    """Landmarks where only the index knuckle (5) is at `index`; knuckles 9, 13 and 17 are at `others`."""
    pts = [P(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    pts[5] = P(x=index[0], y=index[1], z=0.0)
    for i in (9, 13, 17):
        pts[i] = P(x=others[0], y=others[1], z=0.0)
    return pts


def make(**kw):
    m = NullMouse()
    m.position = (900.0, 500.0)
    cfg = ControllerConfig(screen_w=1920, screen_h=1080, region=(0.2, 0.15, 0.8, 0.7), hold_frames=3, cursor_mode="relative",
                           min_cutoff=1.5, beta=50.0, deadzone_px=0.0, **kw)
    return Controller(cfg, m, NullMover()), m


def test_knuckle_average_ignores_a_wobble_of_one_landmark():
    wobble = np.random.default_rng(0).normal(0, 0.004, 90)
    spread = {}
    for point in ("index_knuckle", "knuckles"):
        c, m = make(cursor_point=point)
        xs = []
        for i, w in enumerate(wobble):
            c.step("palm", hand(index=(0.4 + w, 0.4)), i / FPS)
            xs.append(m.position[0])
        spread[point] = np.ptp(xs[30:])
    assert spread["knuckles"] < 0.5 * spread["index_knuckle"]       # four times less weight on the noisy point


def test_knuckle_average_does_not_move_when_the_index_knuckle_shifts_during_a_pinch():
    c, m = make(cursor_point="knuckles")
    for i in range(10):
        c.step("palm", hand(), i / FPS)
    before = m.position
    for i in range(10, 14):                                           # pinching drags the INDEX knuckle sideways
        c.step("palm", hand(index=(0.4 + 0.004 * (i - 9), 0.4)), i / FPS)
    assert abs(m.position[0] - before[0]) < 0.5 * 0.016 * 3200 * 1.2   # moved far less than the index knuckle did


def pinch_sequence(c, t0=0.0, drift=0.02):
    """Hold still (aiming), then form a pinch during which the cursor point drifts, then it is recognised as a click."""
    t = t0
    for _ in range(12):
        c.step("palm", hand(), t)
        t += 1 / FPS
    for k in range(1, 4):                                              # the hand drifts while the pinch forms (3 frames)
        c.step("palm", hand(index=(0.4 + drift * k / 3, 0.4 + drift * k / 3)), t)
        t += 1 / FPS
    c.step("click", hand(index=(0.4 + drift, 0.4 + drift)), t)
    c.step("click", hand(index=(0.4 + drift, 0.4 + drift)), t + 1 / FPS)
    c.step("click", hand(index=(0.4 + drift, 0.4 + drift)), t + 2 / FPS)    # 3rd frame: the click is recognised
    return t + 2 / FPS


def test_click_lands_where_you_were_aiming_not_where_the_pinch_pushed_the_hand():
    with_snap, ms = make(click_lookback_s=0.15)
    pinch_sequence(with_snap)
    plain, mp = make(click_lookback_s=0.0)
    pinch_sequence(plain)
    assert ms.is_down and mp.is_down
    aim = (900.0, 500.0)                                               # where the cursor rested before the pinch
    err_snap = np.hypot(ms.position[0] - aim[0], ms.position[1] - aim[1])
    err_plain = np.hypot(mp.position[0] - aim[0], mp.position[1] - aim[1])
    assert err_plain > 25                                              # without it the click is clearly off target
    assert err_snap < 0.25 * err_plain                                 # with it the click is on target


def test_no_snap_back_when_you_are_really_moving():
    c, m = make(click_lookback_s=0.15, click_snap_px=100)
    t = 0.0
    for _ in range(6):
        c.step("palm", hand(), t)
        t += 1 / FPS
    for i in range(1, 12):                                             # a fast, deliberate move right...
        c.step("palm", hand(index=(0.4 + 0.03 * i, 0.4), others=(0.4 + 0.03 * i, 0.4)), t)
        t += 1 / FPS
    x_moving = m.position[0]
    end = (0.4 + 0.03 * 11, 0.4)
    for _ in range(3):                                                 # ...and click while still on the move
        c.step("click", hand(index=end, others=end), t)
        t += 1 / FPS
    assert m.is_down and m.position[0] > 900 + 150                     # the click was not dragged back to where it started
    assert abs(m.position[0] - x_moving) < 150


def test_right_click_also_lands_on_target():
    c, m = make(click_lookback_s=0.15)
    t = 0.0
    for _ in range(12):
        c.step("palm", hand(), t)
        t += 1 / FPS
    for k in range(1, 4):
        c.step("palm", hand(index=(0.4 + 0.006 * k, 0.4)), t)
        t += 1 / FPS
    for _ in range(3):
        c.step("right", hand(index=(0.418, 0.4)), t)
        t += 1 / FPS
    assert m.right_clicks == 1
    assert abs(m.position[0] - 900) < 15


def test_absolute_mode_is_not_affected_by_the_snap():
    m = NullMouse()
    cfg = ControllerConfig(screen_w=1000, screen_h=1000, region=(0, 0, 1, 1), hold_frames=2, click_lookback_s=0.15)
    c = Controller(cfg, m, NullMover())
    for i in range(6):
        c.step("palm", hand(index=(0.25, 0.75)), i / FPS)
    assert abs(m.position[0] - 250) < 5 and abs(m.position[1] - 750) < 5
