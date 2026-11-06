"""Entry point of the installed program (Hexra.exe).

    Hexra.exe              start the app (rule-based recogniser); no terminal window, only the camera window
    Hexra.exe --dry-run    ...but never touch the mouse
    Hexra.exe enroll       (re)enrol the admin face    (--add to add samples, --clear to forget)
    Hexra.exe precision    measure how steady the cursor point is on your camera
    Hexra.exe selftest     check that every part loads (no camera needed); also writes data\\selftest.log
    Hexra.exe uninstall    remove the program

The installed program is a WINDOWED program (no console). A console is opened only for the commands that print or ask
something (enroll, precision, selftest, uninstall, --help, or the face lock's first-time enrolment). Problems are shown in
a message box and saved to data\\last_error.log instead of in a terminal that would vanish.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "Hexra"
WINDOWED = getattr(sys, "frozen", False) and (sys.stdout is None or sys.stdin is None)   # a --noconsole build has no standard streams
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Hexra"
CONSOLE_COMMANDS = {"selftest", "uninstall", "enroll", "precision"}
_own_console = False      # we opened a console window of our own (so it vanishes when we exit)
_have_console = False     # a console (ours or the terminal we were started from) is attached

if getattr(sys, "frozen", False):
    # mediapipe imports matplotlib only for plotting helpers this app never uses; the installed program leaves
    # matplotlib out (it is big), so give mediapipe empty stand-ins to import.
    import types

    for _name in ("matplotlib", "matplotlib.pyplot"):
        sys.modules.setdefault(_name, types.ModuleType(_name))


def base_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def _quiet_streams() -> None:
    """With no console, print() and logging's console handler must have somewhere harmless to write."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _attach_console() -> None:
    """Give this windowed program a console: the terminal it was started from, or else a new window."""
    global _own_console, _have_console
    import ctypes

    _have_console = True
    k = ctypes.windll.kernel32
    if not k.AttachConsole(-1):                       # ATTACH_PARENT_PROCESS
        k.AllocConsole()
        _own_console = True
    sys.stdout = sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
    sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
    k.SetConsoleTitleW(APP_NAME)


def _dialog(title: str, text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text[:1800], title, 0x10)     # MB_ICONERROR
    except Exception:
        pass


def _face_lock_on() -> bool:
    """Does this run need the console for the face lock's first-time enrolment prompts?"""
    if "--no-face-lock" in sys.argv:
        return False
    try:
        import yaml

        data = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8-sig")) or {}
        return bool((data.get("face_lock") or {}).get("enabled", True))
    except Exception:
        return True


def selftest() -> int:
    import cv2
    import numpy as np
    from hexra.app import load_config
    from hexra.controller import Controller
    from hexra.poses import RuleRecognizer
    from hexra.tracker import HandTracker

    lines = []

    def say(text):
        lines.append(text)
        print(text)

    cfg = load_config("config.yaml")
    say(f"config loaded: {cfg.screen_w} x {cfg.screen_h}")
    tr = HandTracker("models/hand_landmarker.task")
    tr.detect(np.zeros((480, 640, 3), np.uint8), 1)
    tr.close()
    say("hand tracker loaded and ran on an empty picture")
    say(f"pose recogniser and controller classes: {RuleRecognizer.__name__} {Controller.__name__}")
    say("SELFTEST OK")
    Path("data").mkdir(exist_ok=True)
    Path("data/selftest.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def uninstall() -> int:
    import winreg

    base = base_dir()
    print(f"This removes {APP_NAME} from {base}, including your saved face fingerprints, settings and logs.")
    if input("Type y to continue: ").strip().lower() != "y":
        print("Nothing removed.")
        if _own_console:
            time.sleep(2)
        return 0
    import shutil

    shutil.rmtree(Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Hexra",
                  ignore_errors=True)
    desk = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                          capture_output=True, text=True, creationflags=0x08000000).stdout.strip()
    if desk:
        (Path(desk) / "Hexra.lnk").unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    os.chdir(base.parent)
    # A running program cannot delete itself: a detached helper deletes the folder a few seconds after we exit.
    subprocess.Popen(f'cmd /c ping -n 7 127.0.0.1 >nul & rmdir /s /q "{base}"', shell=True,
                     creationflags=0x00000008 | 0x08000000)   # DETACHED_PROCESS | CREATE_NO_WINDOW
    print("Removed. Thank you for trying it.")
    if _own_console:
        time.sleep(3)                                          # long enough to read, shorter than the helper's wait
    return 0


def main() -> int:
    os.chdir(base_dir())
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if WINDOWED:
        if cmd in CONSOLE_COMMANDS or any(a in ("-h", "--help") for a in sys.argv[1:]) or _face_lock_on():
            _attach_console()
        else:
            _quiet_streams()
    if cmd == "selftest":
        return selftest()
    if cmd == "uninstall":
        return uninstall()
    if cmd == "enroll":
        sys.argv = ["enroll_face"] + sys.argv[2:]
        from hexra.enroll_face import main as run
    elif cmd == "precision":
        sys.argv = ["precision"] + sys.argv[2:]
        from hexra.precision import main as run
    else:
        if "--rule" not in sys.argv:
            sys.argv.append("--rule")
        from hexra.app import main as run
    run()
    return 0


def _report(code, message: str) -> None:
    """Tell the user what went wrong: in the console if there is one, otherwise in a message box and a log file."""
    has_console = not WINDOWED or _have_console
    try:
        Path("data").mkdir(exist_ok=True)
        with open(Path("data") / "last_error.log", "w", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass
    if has_console:
        print(message)
        if _own_console or not WINDOWED:
            try:
                input("\nSomething went wrong (details above and in data\\last_error.log). Press Enter to close.")
            except Exception:
                pass
    else:
        first = message.strip().splitlines()[-1] if message.strip() else f"error code {code}"
        _dialog("Hexra could not start", f"{first}\n\nDetails were saved to:\n{Path('data').resolve() / 'last_error.log'}")


if __name__ == "__main__":
    code = 0
    try:
        code = main()
    except SystemExit as e:
        if isinstance(e.code, int):
            code = e.code
            if code:
                _report(code, f"Hexra stopped with error code {code}.")
        elif e.code is None:
            code = 0
        else:
            code = 1
            _report(code, str(e.code))
    except Exception:
        import traceback

        code = 1
        _report(code, traceback.format_exc())
    sys.exit(code)
