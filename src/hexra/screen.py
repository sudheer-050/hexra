"""Screen geometry: the main screen, every extra screen, and the combined desktop.

All numbers are physical pixels in Windows' "virtual desktop" coordinates: the main screen's top-left is (0, 0), and a
screen to its left or above has NEGATIVE coordinates.
"""
from __future__ import annotations

import sys


def enable_dpi_awareness() -> None:
    """On Windows, make pixel coordinates match the real screens (no display scaling), even when screens differ in scaling."""
    if sys.platform != "win32":
        return
    import ctypes

    try:                                                         # best: each monitor reports its own true pixels
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):   # PER_MONITOR_AWARE_V2
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)           # per-monitor
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def get_screen_size(width: int | None = None, height: int | None = None) -> tuple[int, int]:
    """Return (width, height) of the main screen. Config overrides win; otherwise ask tkinter."""
    if width and height:
        return width, height
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        try:
            return root.winfo_screenwidth(), root.winfo_screenheight()
        finally:
            root.destroy()
    except Exception as exc:
        raise RuntimeError(
            "Could not detect the screen size. Set screen.width and screen.height "
            "in config.yaml."
        ) from exc


def list_monitors() -> list:
    """Every connected screen as (left, top, width, height, is_primary). Empty if it cannot be read."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        found = []
        proto = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT),
                                   ctypes.c_void_p)

        def callback(hmon, hdc, rect, lparam):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(info)):
                r = info.rcMonitor
                found.append((r.left, r.top, r.right - r.left, r.bottom - r.top, bool(info.dwFlags & 1)))
            return 1

        ctypes.windll.user32.EnumDisplayMonitors(None, None, proto(callback), 0)
        return found
    except Exception:
        return []


def _ordered(monitors: list) -> list:
    """Numbering used by `screen.monitor`: 1 = the main screen, then the others from left to right (top to bottom)."""
    primary = [m for m in monitors if m[4]] or monitors[:1]
    others = sorted((m for m in monitors if m not in primary), key=lambda m: (m[0], m[1]))
    return primary + others


def screen_rect(span: str = "all", monitor=None, monitors=None, manual=None) -> tuple:
    """The area the hand controls, as (left, top, width, height).

    span "all"     the whole combined desktop (every screen, including ones at negative coordinates)
    span "primary" the main screen only
    monitor N      just screen number N (1 = main screen, then left to right)
    manual         (width, height, left, top) from the config, wins over everything
    """
    if manual and manual[0] and manual[1]:
        return (int(manual[2] or 0), int(manual[3] or 0), int(manual[0]), int(manual[1]))
    monitors = list_monitors() if monitors is None else monitors
    if not monitors:
        w, h = get_screen_size()
        return (0, 0, w, h)
    ordered = _ordered(monitors)
    if monitor is not None:
        if not 1 <= int(monitor) <= len(ordered):
            raise ValueError(f"screen.monitor is {monitor}, but only {len(ordered)} screen(s) are connected")
        left, top, w, h, _ = ordered[int(monitor) - 1]
        return (left, top, w, h)
    if str(span).lower() == "primary":
        left, top, w, h, _ = ordered[0]
        return (left, top, w, h)
    left = min(m[0] for m in monitors)
    top = min(m[1] for m in monitors)
    right = max(m[0] + m[2] for m in monitors)
    bottom = max(m[1] + m[3] for m in monitors)
    return (left, top, right - left, bottom - top)
