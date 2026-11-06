"""Several screens, tested with SIMULATED layouts (the real PC has one screen)."""
import math
from types import SimpleNamespace as P

import pytest

from hexra.actions import NullMouse
from hexra.controller import Controller, ControllerConfig
from hexra.screen import _ordered, list_monitors, screen_rect
from hexra.windows import NullMover

MAIN = (0, 0, 2560, 1600, True)
RIGHT = (2560, 0, 1920, 1080, False)            # a second screen to the right
LEFT = (-1920, 0, 1920, 1080, False)            # ...to the left (negative x)
ABOVE = (0, -1080, 1920, 1080, False)           # ...above (negative y)


def test_single_screen_is_unchanged():
    assert screen_rect(monitors=[MAIN]) == (0, 0, 2560, 1600)


def test_second_screen_on_the_right_extends_the_area():
    assert screen_rect(monitors=[MAIN, RIGHT]) == (0, 0, 4480, 1600)


def test_second_screen_on_the_left_has_negative_coordinates():
    assert screen_rect(monitors=[MAIN, LEFT]) == (-1920, 0, 4480, 1600)


def test_second_screen_above():
    assert screen_rect(monitors=[MAIN, ABOVE]) == (0, -1080, 2560, 2680)


def test_three_screens():
    assert screen_rect(monitors=[LEFT, MAIN, RIGHT]) == (-1920, 0, 6400, 1600)


def test_primary_only_and_single_screen_choice():
    both = [RIGHT, MAIN]                                       # the order Windows lists them in does not matter
    assert screen_rect("primary", monitors=both) == (0, 0, 2560, 1600)
    assert screen_rect(monitor=1, monitors=both) == (0, 0, 2560, 1600)
    assert screen_rect(monitor=2, monitors=both) == (2560, 0, 1920, 1080)
    assert [m[0] for m in _ordered([RIGHT, LEFT, MAIN])] == [0, -1920, 2560]      # main first, then left to right


def test_bad_screen_number_and_manual_override():
    with pytest.raises(ValueError, match="only 1 screen"):
        screen_rect(monitor=2, monitors=[MAIN])
    assert screen_rect(monitors=[MAIN, RIGHT], manual=(1000, 800, 10, 20)) == (10, 20, 1000, 800)


def test_this_pcs_real_screens_are_read():
    mons = list_monitors()
    assert mons and any(m[4] for m in mons)                    # at least one, and one is the main screen
    left, top, w, h = screen_rect()
    assert w > 0 and h > 0


# ---- the controller on a multi-screen area ---------------------------------------------------------------
def lm(x, y):
    pts = [P(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    pts[5] = P(x=x, y=y, z=0.0)
    return pts


def controller(rect, mode, mouse=None, start=None):
    left, top, w, h = rect
    m = mouse or NullMouse()
    if start:
        m.position = start
    cfg = ControllerConfig(screen_x=left, screen_y=top, screen_w=w, screen_h=h, region=(0, 0, 1, 1), hold_frames=2,
                           cursor_mode=mode, min_cutoff=1.5, beta=50.0, deadzone_px=0.0)
    return Controller(cfg, m, NullMover()), m


def test_absolute_mode_reaches_both_edges_including_negative_ones():
    c, m = controller((-1920, 0, 4480, 1600), "absolute")
    for i in range(8):
        c.step("palm", lm(0.0, 0.5), i / 30)
    assert abs(m.position[0] - (-1920)) < 3                    # far left = the left screen's left edge
    for i in range(8, 16):
        c.step("palm", lm(1.0, 0.5), i / 30)
    assert abs(m.position[0] - (4480 - 1920 - 1)) < 3          # far right = the main screen's right edge


def test_relative_mode_crosses_onto_the_second_screen_and_stops_at_the_edges():
    c, m = controller((0, 0, 4480, 1600), "relative", start=(2000.0, 800.0))
    t = 0.0
    for _ in range(5):
        c.step("palm", lm(0.3, 0.5), t)
        t += 1 / 30
    for i in range(1, 16):                                      # a fast flick right
        c.step("palm", lm(0.3 + 0.03 * i, 0.5), t)
        t += 1 / 30
    assert m.position[0] > 2560                                 # it is on the second screen
    for i in range(1, 40):
        c.step("palm", lm(0.75 + 0.01 * (i % 3), 0.5), t)
        t += 1 / 30
    assert m.position[0] <= 4479.0                              # and never goes past the last screen's edge


def test_relative_mode_works_on_a_left_screen_with_negative_coordinates():
    c, m = controller((-1920, 0, 4480, 1600), "relative", start=(200.0, 800.0))
    t = 0.0
    for _ in range(5):
        c.step("palm", lm(0.7, 0.5), t)
        t += 1 / 30
    for i in range(1, 25):                                      # flick LEFT
        c.step("palm", lm(0.7 - 0.025 * i, 0.5), t)
        t += 1 / 30
    assert m.position[0] < 0                                    # moved onto the left screen
    assert m.position[0] >= -1920.0


class ClampingMouse(NullMouse):
    """Like Windows: when asked to go where there is no screen, the cursor lands on the nearest screen edge."""

    def __init__(self, screens):
        super().__init__()
        self.screens = screens

    def move(self, x, y):
        best = None
        for (left, top, w, h, _) in self.screens:
            cx, cy = min(max(x, left), left + w - 1), min(max(y, top), top + h - 1)
            d = math.hypot(cx - x, cy - y)
            if best is None or d < best[0]:
                best = (d, cx, cy)
        self.position = (best[1], best[2])


def test_dead_area_between_unequal_screens_does_not_trap_the_cursor():
    screens = [MAIN, (2560, 0, 1920, 1080, False)]              # the right screen is shorter: the area below it is empty
    c, m = controller((0, 0, 4480, 1600), "relative", mouse=ClampingMouse(screens), start=(3000.0, 500.0))
    t = 0.0
    for _ in range(5):
        c.step("palm", lm(0.7, 0.3), t)
        t += 1 / 30
    for i in range(1, 30):                                      # push the hand far DOWN, into the empty corner
        c.step("palm", lm(0.7, 0.3 + 0.02 * i), t)
        t += 1 / 30
    assert m.position[1] <= 1079                                # Windows kept it on the shorter screen
    y_at_edge = m.position[1]
    for i in range(1, 6):                                       # now move back UP: it must respond at once
        c.step("palm", lm(0.7, 0.9 - 0.02 * i), t)
        t += 1 / 30
    assert m.position[1] < y_at_edge - 30


def test_default_config_describes_the_whole_desktop():
    from hexra.app import load_config

    cfg = load_config("config.yaml")
    left, top, w, h = screen_rect()
    assert (cfg.screen_x, cfg.screen_y, cfg.screen_w, cfg.screen_h) == (left, top, w, h)
