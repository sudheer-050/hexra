"""Entry point of the installed program (Hexra.exe).

    Hexra.exe              start the app (rule-based recogniser)
    Hexra.exe --dry-run    ...but never touch the mouse
    Hexra.exe enroll       (re)enrol the admin face    (--add to add samples, --clear to forget)
    Hexra.exe precision    measure how steady the cursor point is on your camera
    Hexra.exe selftest     check that every part loads (no camera needed)
    Hexra.exe uninstall    remove the program
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "Hexra"

if getattr(sys, "frozen", False):
    # mediapipe imports matplotlib only for plotting helpers this app never uses; the installed program leaves
    # matplotlib out (it is big), so give mediapipe empty stand-ins to import.
    import types

    for _name in ("matplotlib", "matplotlib.pyplot"):
        sys.modules.setdefault(_name, types.ModuleType(_name))
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Hexra"


def base_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def selftest() -> int:
    import cv2
    import numpy as np
    from hexra.app import load_config
    from hexra.controller import Controller
    from hexra.poses import RuleRecognizer
    from hexra.tracker import HandTracker

    cfg = load_config("config.yaml")
    print("config loaded:", cfg.screen_w, "x", cfg.screen_h)
    tr = HandTracker("models/hand_landmarker.task")
    tr.detect(np.zeros((480, 640, 3), np.uint8), 1)
    tr.close()
    print("hand tracker loaded and ran on an empty picture")
    print("pose recogniser and controller classes:", RuleRecognizer.__name__, Controller.__name__)
    print("SELFTEST OK")
    return 0


def uninstall() -> int:
    import winreg

    base = base_dir()
    print(f"This removes {APP_NAME} from {base}, including your saved face fingerprints, settings and logs.")
    if input("Type y to continue: ").strip().lower() != "y":
        print("Nothing removed.")
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
    # A running program cannot delete itself: a detached helper deletes the folder a moment after we exit.
    subprocess.Popen(f'cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "{base}"', shell=True,
                     creationflags=0x00000008 | 0x08000000)   # DETACHED_PROCESS | CREATE_NO_WINDOW
    print("Removed. Thank you for trying it.")
    return 0


def main() -> int:
    os.chdir(base_dir())
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
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


if __name__ == "__main__":
    code = 0
    try:
        code = main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if e.code not in (None, 0):
            print(e.code if not isinstance(e.code, int) else "")
    except Exception:
        import traceback

        traceback.print_exc()
        code = 1
    if code:
        input("\nSomething went wrong (details above and in data\last_run.log). Press Enter to close.")
    sys.exit(code)
