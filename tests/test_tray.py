"""The Windows tray icon: really adds an icon to the notification area, answers clicks and menu commands, and removes itself."""
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows tray icon")

from hexra import tray  # noqa: E402

ICON = Path(__file__).resolve().parent.parent / "packaging" / "app.ico"


def make(events, state=None):
    return tray.Tray(ICON, lambda: events.append("open"), lambda: events.append("toggle"), lambda: events.append("startstop"),
                     lambda: events.append("quit"), state or (lambda: {"running": True, "engaged": True, "tip": "Hexra: controlling"}))


def wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_the_icon_is_added_and_clicks_and_menu_commands_reach_the_app():
    import ctypes
    events = []
    t = make(events)
    assert t.start() and t.ok                                   # Windows accepted the icon
    try:
        post = ctypes.windll.user32.PostMessageW
        post(t.hwnd, tray.WM_APP_TRAY, 1, tray.WM_LBUTTONUP)     # a left click on the icon
        assert wait(lambda: "open" in events)
        for cmd, name in ((tray.ID_TOGGLE, "toggle"), (tray.ID_STARTSTOP, "startstop"), (tray.ID_QUIT, "quit")):
            post(t.hwnd, tray.WM_COMMAND, cmd, 0)                # the menu items
            assert wait(lambda: name in events), name
    finally:
        t.stop()
    assert not t._thread.is_alive()


def test_the_icon_is_removed_when_stopped():
    t = make([])
    assert t.start()
    assert not t.removed
    t.stop()
    assert t.removed                                             # Windows confirmed the icon was deleted from the tray


def test_the_tooltip_shows_the_apps_state_and_survives_a_failing_state_function():
    t = make([], state=lambda: {"tip": "Hexra: paused"})
    assert t._tooltip() == "Hexra: paused"
    broken = make([], state=lambda: 1 / 0)
    assert broken._tooltip() == "Hexra"
