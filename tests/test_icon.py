"""The window/taskbar icon helper must find the icon file and must never raise, whatever the window or platform."""
from hexra import icon


def test_the_icon_file_is_found():
    path = icon.find_icon()
    assert path is not None and path.exists() and path.suffix == ".ico"


def test_calls_with_no_window_do_nothing_and_do_not_raise():
    assert icon.apply_to_hwnd(0) is False
    assert icon.apply_to_window("a window title that does not exist", wait_s=0.1) is False
    icon.set_app_id()               # no exception
    icon.apply_to_console()         # no exception (a console may or may not exist)
