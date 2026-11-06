"""Window and taskbar icon (Windows only; every call quietly does nothing elsewhere or on failure).

An .exe carries its icon in the file, but the windows a program draws do not inherit it: OpenCV's camera window and the
console show generic icons, and tkinter shows its own feather. This loads the Hexra icon from disk and sets it on those
windows, and gives the process its own taskbar identity so the taskbar shows the Hexra icon instead of Python's.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

APP_ID = "Hexra.Hexra"
WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010


def find_icon() -> Path | None:
    """The icon file: next to the installed program, or in the project's packaging folder when running from source."""
    here = Path(__file__).resolve()
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "Hexra.ico")
    candidates += [here.parent / "hexra.ico", here.parents[2] / "packaging" / "app.ico"]
    return next((c for c in candidates if c.exists()), None)


def set_app_id(app_id: str = APP_ID) -> None:
    """Make the taskbar treat this process as its own app (so it shows its own icon, not python.exe's)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def apply_to_hwnd(hwnd, ico: Path | None = None) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    ico = ico or find_icon()
    if ico is None:
        return False
    try:
        import ctypes

        u = ctypes.windll.user32
        u.LoadImageW.restype = ctypes.c_void_p
        u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        ok = False
        for kind, metric in ((ICON_BIG, 11), (ICON_SMALL, 49)):          # SM_CXICON, SM_CXSMICON
            size = u.GetSystemMetrics(metric)
            handle = u.LoadImageW(None, str(ico), IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if handle:
                u.SendMessageW(hwnd, WM_SETICON, kind, handle)
                ok = True
        return ok
    except Exception:
        return False


def apply_to_window(title: str, wait_s: float = 3.0) -> bool:
    """Set the icon on the top-level window with this exact title (waits briefly for it to exist)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        find = ctypes.windll.user32.FindWindowW
        find.restype = ctypes.c_void_p
        end = time.time() + wait_s
        while True:
            hwnd = find(None, title)
            if hwnd:
                return apply_to_hwnd(hwnd)
            if time.time() > end:
                return False
            time.sleep(0.05)
    except Exception:
        return False


def apply_to_console() -> bool:
    """The console window (classic console only; Windows Terminal draws its own icon)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        return apply_to_hwnd(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        return False
