"""Start Hexra when you log in to Windows: one value in the current user's Run key (no administrator rights, nothing system-wide).

Hexra starts straight into the system tray with no window (--background). Turning it off removes the value again.
"""
from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Hexra"


def available() -> bool:
    return sys.platform == "win32"


def command(exe: Path) -> str:
    return f'"{exe}" --background'


def is_enabled(key: str = RUN_KEY, value: str = VALUE) -> bool:
    if not available():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.QueryValueEx(k, value)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool, exe: Path, key: str = RUN_KEY, value: str = VALUE) -> None:
    import winreg

    if enabled:
        if not Path(exe).exists():
            raise RuntimeError("Start with Windows is only available in the installed Hexra.")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, value, 0, winreg.REG_SZ, command(Path(exe)))
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, value)
        except OSError:
            pass                                    # it was not set: nothing to remove
