"""How the settings window and the control engine talk when Hexra runs as one application.

The engine (a separate process, so a camera or tracker crash can never take the window down) writes the newest camera picture
to data/preview.jpg and its state to data/status.json; the window reads them. The window asks the engine to stop or to pause
by creating small flag files that the engine removes when it has acted on them. Everything is local files in data/, no sockets.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

DATA = Path("data")
PREVIEW, STATUS = "preview.jpg", "status.json"
STOP, TOGGLE = "ctl_stop", "ctl_toggle"


def write_atomic(path: Path, payload: bytes) -> bool:
    """Replace a file in one step so a reader never sees half of it. False when the reader had it open at that instant."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def write_status(base: Path, **fields) -> None:
    fields["time"] = time.time()
    write_atomic(base / STATUS, json.dumps(fields).encode("utf-8"))


def read_status(base: Path, max_age_s: float = 3.0) -> dict:
    """The engine's last status, or {} when it is old (the engine is gone) or missing."""
    try:
        d = json.loads((base / STATUS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if time.time() - d.get("time", 0) <= max_age_s else {}


def request(base: Path, flag: str) -> None:
    (base / flag).write_text("1", encoding="utf-8")


def consume(base: Path, flag: str) -> bool:
    """True once if the flag was set; clears it."""
    p = base / flag
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
        return True
    return False


def clear_all(base: Path) -> None:
    for name in (STOP, TOGGLE, STATUS, PREVIEW):
        try:
            (base / name).unlink()
        except OSError:
            pass


def process_alive(pid: int) -> bool:
    """Is that process still running? (Used so the engine quits when the window that started it is gone.)"""
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes

    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)        # SYNCHRONIZE
    if not h:
        return False
    try:
        return k.WaitForSingleObject(h, 0) == 0x102   # WAIT_TIMEOUT: still running
    finally:
        k.CloseHandle(h)
