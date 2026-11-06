"""A system-tray icon for Windows with plain ctypes (no extra libraries).

Left click opens the Hexra window; right click shows a menu (Open, Pause/Resume, Start/Stop, Quit). The icon lives on its own
thread with its own message loop, so nothing here ever blocks the app. Callbacks are called on that thread: keep them short.
"""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from pathlib import Path

WM_APP_TRAY = 0x8001            # WM_APP + 1: what Windows sends us about the icon
WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0205, 0x0203
WM_COMMAND, WM_TIMER, WM_CLOSE, WM_DESTROY, WM_NULL = 0x0111, 0x0113, 0x0010, 0x0002, 0x0000
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
MF_STRING, MF_GRAYED, MF_SEPARATOR = 0, 1, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_BOTTOMALIGN = 0x0002, 0x0100, 0x0020
ID_OPEN, ID_TOGGLE, ID_STARTSTOP, ID_QUIT = 1001, 1002, 1003, 1004
LRESULT = ctypes.c_ssize_t


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uTimeout", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


def available() -> bool:
    return sys.platform == "win32"


class Tray:
    """state() -> dict(running, engaged, dry, tip) is read for the tooltip and the menu each time it is shown."""

    def __init__(self, icon_path, on_open, on_toggle, on_startstop, on_quit, state, tip="Hexra"):
        self.icon_path, self.tip = Path(icon_path), tip
        self.on_open, self.on_toggle, self.on_startstop, self.on_quit, self.state = on_open, on_toggle, on_startstop, on_quit, state
        self.hwnd = None
        self.ok = False
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._nid = None
        self._taskbar_created = 0
        self.removed = False
        self._wndproc = WNDPROC(self._proc)             # keep a reference: ctypes must not free it while the window exists

    # ---- public
    def start(self, timeout: float = 5.0) -> bool:
        self._thread.start()
        self._ready.wait(timeout)
        return self.ok

    def stop(self) -> None:
        if self.hwnd:
            ctypes.windll.user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self._thread.join(timeout=3)

    # ---- internals
    def _load_icon(self):
        u = ctypes.windll.user32
        u.LoadImageW.restype = wintypes.HANDLE
        u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        if self.icon_path.exists():
            h = u.LoadImageW(None, str(self.icon_path), 1, 0, 0, 0x10 | 0x40)       # IMAGE_ICON, LR_LOADFROMFILE | LR_DEFAULTSIZE
            if h:
                return h
        u.LoadIconW.restype = wintypes.HANDLE
        return u.LoadIconW(None, ctypes.c_void_p(32512))                              # the stock application icon

    def _data(self, flags=NIF_MESSAGE | NIF_ICON | NIF_TIP):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd, nid.uID, nid.uFlags, nid.uCallbackMessage = self.hwnd, 1, flags, WM_APP_TRAY
        nid.hIcon = self._icon
        nid.szTip = self._tooltip()[:127]
        return nid

    def _tooltip(self) -> str:
        try:
            return self.state().get("tip") or self.tip
        except Exception:
            return self.tip

    def _run(self) -> None:
        u, k, s = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.shell32
        u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.DefWindowProcW.restype = LRESULT
        u.CreateWindowExW.restype = wintypes.HWND
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
        u.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        u.CreatePopupMenu.restype = wintypes.HMENU
        u.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
        s.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        k.GetModuleHandleW.restype = wintypes.HINSTANCE
        hinst = k.GetModuleHandleW(None)
        self._icon = self._load_icon()
        cls = WNDCLASSW()
        cls.lpfnWndProc, cls.hInstance, cls.lpszClassName = self._wndproc, hinst, "HexraTrayWindow"
        u.RegisterClassW(ctypes.byref(cls))
        self.hwnd = u.CreateWindowExW(0, "HexraTrayWindow", "Hexra", 0, 0, 0, 0, 0, None, None, hinst, None)   # hidden: never shown
        self._taskbar_created = u.RegisterWindowMessageW("TaskbarCreated")
        if not self.hwnd:
            self._ready.set()
            return
        self.ok = bool(s.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._data())))
        u.SetTimer(self.hwnd, 1, 3000, None)                                                # refresh the tooltip
        self._ready.set()
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))
        u.UnregisterClassW("HexraTrayWindow", hinst)      # the class points at THIS object's window procedure; free it for the next one

    def _menu(self) -> None:
        u = ctypes.windll.user32
        try:
            st = self.state()
        except Exception:
            st = {}
        m = u.CreatePopupMenu()
        u.AppendMenuW(m, MF_STRING, ID_OPEN, "Open Hexra")
        u.AppendMenuW(m, MF_SEPARATOR, 0, None)
        running = bool(st.get("running"))
        if running and not st.get("dry"):
            u.AppendMenuW(m, MF_STRING, ID_TOGGLE, "Pause control" if st.get("engaged") else "Resume control")
        u.AppendMenuW(m, MF_STRING, ID_STARTSTOP, "Stop camera and tracking" if running else "Start Hexra")
        u.AppendMenuW(m, MF_SEPARATOR, 0, None)
        u.AppendMenuW(m, MF_STRING, ID_QUIT, "Quit Hexra")
        pt = wintypes.POINT()
        u.GetCursorPos(ctypes.byref(pt))
        u.SetForegroundWindow(self.hwnd)                                                   # or the menu does not close when clicking elsewhere
        cmd = u.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_BOTTOMALIGN, pt.x, pt.y, 0, self.hwnd, None)
        u.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        u.DestroyMenu(m)
        if cmd:
            self._command(cmd)

    def _command(self, cmd: int) -> None:
        try:
            {ID_OPEN: self.on_open, ID_TOGGLE: self.on_toggle, ID_STARTSTOP: self.on_startstop, ID_QUIT: self.on_quit}[cmd]()
        except Exception:
            pass

    def _proc(self, hwnd, msg, wparam, lparam):
        u, s = ctypes.windll.user32, ctypes.windll.shell32
        if msg == WM_APP_TRAY:
            if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._command(ID_OPEN)
            elif lparam == WM_RBUTTONUP:
                self._menu()
            return 0
        if msg == WM_COMMAND:
            self._command(wparam & 0xFFFF)
            return 0
        if msg == WM_TIMER:
            s.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._data(NIF_TIP)))
            return 0
        if self._taskbar_created and msg == self._taskbar_created:                                                   # Explorer restarted: put the icon back
            s.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._data()))
            return 0
        if msg == WM_CLOSE:
            self.removed = bool(s.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data(0))))
            u.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            u.PostQuitMessage(0)
            return 0
        return u.DefWindowProcW(hwnd, msg, wparam, lparam)
