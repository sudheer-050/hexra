"""Move the window under the cursor. Win32Mover uses ctypes (Windows only); NullMover records for tests/dry-run."""
from __future__ import annotations

import sys

_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}  # desktop and taskbar


class NullMover:
    def __init__(self):
        self.grabbed = None
        self.position = None

    def grab(self):
        self.grabbed = True
        self.position = (0, 0)
        return (0, 0)

    def move_to(self, x, y):
        self.position = (round(x), round(y))

    def release(self):
        self.grabbed = None


class Win32Mover:
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
    SW_RESTORE = 9

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self._ct, self._wt = ctypes, wintypes
        self._u = ctypes.windll.user32
        self._hwnd = None

    def _class_name(self, hwnd) -> str:
        buf = self._ct.create_unicode_buffer(256)
        self._u.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def grab(self):
        """Grab the window under the mouse cursor. Returns its (x, y) top-left, or None if nothing safe to move."""
        pt = self._wt.POINT()
        if not self._u.GetCursorPos(self._ct.byref(pt)):
            return None
        hwnd = self._u.WindowFromPoint(pt)
        if hwnd:
            hwnd = self._u.GetAncestor(hwnd, 2)  # GA_ROOT: the top-level window, not a button/tab inside it
        if not hwnd or self._class_name(hwnd) in _SKIP_CLASSES:
            return None
        if self._u.IsZoomed(hwnd):
            self._u.ShowWindow(hwnd, self.SW_RESTORE)  # a maximised window cannot be moved
        rect = self._wt.RECT()
        if not self._u.GetWindowRect(hwnd, self._ct.byref(rect)):
            return None
        self._hwnd = hwnd
        return rect.left, rect.top

    def move_to(self, x, y):
        if self._hwnd:
            self._u.SetWindowPos(self._hwnd, 0, int(x), int(y), 0, 0,
                                 self.SWP_NOSIZE | self.SWP_NOZORDER | self.SWP_NOACTIVATE)

    def release(self):
        self._hwnd = None


def make_mover():
    return Win32Mover() if sys.platform == "win32" else NullMover()
