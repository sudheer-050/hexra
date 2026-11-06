"""Move, snap, maximise, minimise and close the window under the cursor.

Win32Mover uses ctypes (Windows only); NullMover records what it was asked to do, for tests and --dry-run.
"""
from __future__ import annotations

import os
import sys

_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}  # desktop and taskbar


class NullMover:
    """Records everything instead of touching windows. `monitor` is the work area it pretends the cursor is on."""

    def __init__(self):
        self.grabbed = None
        self.position = None
        self.monitor = None        # (left, top, width, height) or None = the controller falls back to its own screen rect
        self.commands = []         # e.g. ["maximize", "snap:left", "minimize", "close"]
        self.target_title = "test window"

    def grab(self):
        self.grabbed = True
        self.position = (0, 0)
        return (0, 0)

    def move_to(self, x, y):
        self.position = (round(x), round(y))

    def release(self):
        self.grabbed = None

    def monitor_rect(self, x, y):
        return self.monitor

    def snap(self, mode):
        self.commands.append("snap:" + mode)
        return f"snapped {mode}: {self.target_title}"

    def toggle_maximize(self):
        self.commands.append("maximize")
        return f"maximised/restored: {self.target_title}"

    def minimize(self):
        self.commands.append("minimize")
        return f"minimised: {self.target_title}"

    def close(self):
        self.commands.append("close")
        return f"closed: {self.target_title}"


def snap_zone(x, y, rect, edge_px):
    """Which edge of the screen `rect` = (left, top, width, height) the point is in: "left", "right", "top" or None.
    A corner counts as the side edge, so dragging into a corner never maximises by accident."""
    left, top, w, h = rect
    if x <= left + edge_px:
        return "left"
    if x >= left + w - 1 - edge_px:
        return "right"
    if y <= top + edge_px:
        return "top"
    return None


class Win32Mover:
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
    SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
    WM_CLOSE = 0x0010
    WS_MAXIMIZEBOX, WS_MINIMIZEBOX = 0x00010000, 0x00020000
    GWL_STYLE = -16
    MONITOR_DEFAULTTONEAREST = 2

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self._ct, self._wt = ctypes, wintypes
        self._u = ctypes.windll.user32
        self._u.WindowFromPoint.argtypes = [wintypes.POINT]          # POINT is passed by value
        self._u.WindowFromPoint.restype = wintypes.HWND
        self._u.GetAncestor.restype = wintypes.HWND
        self._u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        self._u.MonitorFromPoint.restype = wintypes.HANDLE
        self._u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._hwnd = None

    # -- helpers -------------------------------------------------------------------------------------------------------
    def _class_name(self, hwnd) -> str:
        buf = self._ct.create_unicode_buffer(256)
        self._u.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _title(self, hwnd) -> str:
        buf = self._ct.create_unicode_buffer(256)
        self._u.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    def _cursor(self):
        pt = self._wt.POINT()
        return pt if self._u.GetCursorPos(self._ct.byref(pt)) else None

    def _is_ours(self, hwnd) -> bool:
        """Never act on Hexra's own windows (its console and its camera preview)."""
        try:
            if hwnd == self._ct.windll.kernel32.GetConsoleWindow():
                return True
            pid = self._wt.DWORD()
            self._u.GetWindowThreadProcessId(hwnd, self._ct.byref(pid))
            return pid.value == os.getpid() or self._title(hwnd).strip().lower() == "hexra"
        except Exception:
            return False

    def _target(self):
        """The top-level window under the mouse cursor, or None when there is nothing safe to act on."""
        pt = self._cursor()
        if pt is None:
            return None
        hwnd = self._u.WindowFromPoint(pt)
        if hwnd:
            hwnd = self._u.GetAncestor(hwnd, 2)  # GA_ROOT: the top-level window, not a button/tab inside it
        if not hwnd or self._class_name(hwnd) in _SKIP_CLASSES or self._is_ours(hwnd):
            return None
        return hwnd

    def _monitor_info(self, x, y):
        """(full screen, work area) of the screen containing the point, each as (left, top, width, height)."""
        class MONITORINFO(self._ct.Structure):
            _fields_ = [("cbSize", self._wt.DWORD), ("rcMonitor", self._wt.RECT), ("rcWork", self._wt.RECT), ("dwFlags", self._wt.DWORD)]

        info = MONITORINFO()
        info.cbSize = self._ct.sizeof(MONITORINFO)
        mon = self._u.MonitorFromPoint(self._wt.POINT(int(x), int(y)), self.MONITOR_DEFAULTTONEAREST)
        if not mon or not self._u.GetMonitorInfoW(mon, self._ct.byref(info)):
            return None
        box = lambda r: (r.left, r.top, r.right - r.left, r.bottom - r.top)
        return box(info.rcMonitor), box(info.rcWork)

    def monitor_rect(self, x, y):
        """The full screen (taskbar included) under a point, so the edge of the SCREEN is where snapping starts."""
        got = self._monitor_info(x, y)
        return got[0] if got else None

    def _work_area(self, x, y):
        """The screen minus the taskbar, where a snapped window should fit."""
        got = self._monitor_info(x, y)
        return got[1] if got else None

    def _frame_insets(self, hwnd):
        """Windows 10/11 windows have an invisible resize border; return how far the visible frame sits inside the rect."""
        rect, vis = self._wt.RECT(), self._wt.RECT()
        try:
            self._u.GetWindowRect(hwnd, self._ct.byref(rect))
            ok = self._ct.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, self._ct.byref(vis), self._ct.sizeof(vis)) == 0   # DWMWA_EXTENDED_FRAME_BOUNDS
            if ok:
                return vis.left - rect.left, vis.top - rect.top, rect.right - vis.right, rect.bottom - vis.bottom
        except Exception:
            pass
        return 0, 0, 0, 0

    # -- moving a window with a fist ----------------------------------------------------------------------------------
    def grab(self):
        """Grab the window under the mouse cursor. Returns its (x, y) top-left, or None if nothing safe to move."""
        hwnd = self._target()
        if hwnd is None:
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

    # -- snapping the window being held --------------------------------------------------------------------------------
    def snap(self, mode):
        """Snap the window being held: "left"/"right" half of the screen under the cursor, or "maximize"."""
        hwnd = self._hwnd
        pt = self._cursor()
        if not hwnd or pt is None:
            return None
        title = self._title(hwnd)
        if mode == "maximize":
            if self._u.GetWindowLongW(hwnd, self.GWL_STYLE) & self.WS_MAXIMIZEBOX:
                self._u.ShowWindow(hwnd, self.SW_MAXIMIZE)
                return f"snapped to the top (maximised): {title}"
            return None
        area = self._work_area(pt.x, pt.y)
        if area is None:
            return None
        left, top, w, h = area
        half = w // 2
        x = left if mode == "left" else left + half
        width = half if mode == "left" else w - half
        il, it, ir, ib = self._frame_insets(hwnd)
        self._u.SetWindowPos(hwnd, 0, x - il, top - it, width + il + ir, h + it + ib, self.SWP_NOZORDER | self.SWP_NOACTIVATE)
        return f"snapped {mode}: {title}"

    # -- one-shot commands on the window under the cursor --------------------------------------------------------------
    def toggle_maximize(self):
        hwnd = self._target()
        if hwnd is None:
            return None
        title = self._title(hwnd)
        if self._u.IsZoomed(hwnd):
            self._u.ShowWindow(hwnd, self.SW_RESTORE)
            return f"restored: {title}"
        if self._u.GetWindowLongW(hwnd, self.GWL_STYLE) & self.WS_MAXIMIZEBOX:
            self._u.ShowWindow(hwnd, self.SW_MAXIMIZE)
            return f"maximised: {title}"
        return None

    def minimize(self):
        hwnd = self._target()
        if hwnd is None or not (self._u.GetWindowLongW(hwnd, self.GWL_STYLE) & self.WS_MINIMIZEBOX):
            return None
        title = self._title(hwnd)
        self._u.ShowWindow(hwnd, self.SW_MINIMIZE)
        return f"minimised: {title}"

    def close(self):
        """Ask the window to close (WM_CLOSE), exactly like its X button: the program may ask to save first."""
        hwnd = self._target()
        if hwnd is None:
            return None
        title = self._title(hwnd)
        self._u.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)
        return f"close requested: {title}"


def make_mover():
    return Win32Mover() if sys.platform == "win32" else NullMover()
