"""The Hexra application window: settings, live camera and controls in one page, served locally.

It listens only on 127.0.0.1 on a random port, answers only requests that carry this run's secret token and the right Host
header, and closes itself when its window has been closed. Everything it can change goes through settings_schema validation
and config_io's comment-preserving writer, so it can only ever write settings listed in the catalogue.

The control engine (camera, hand tracking, mouse) runs as a separate process started from here, so a camera or tracker problem
can never take the window down. See ipc.py for how the two talk.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import autostart, config_io, ipc, settings_schema as schema
from .tray import Tray, available as tray_available

UI_DIR = Path(__file__).resolve().parent / "ui"
IDLE_QUIT_S = 150.0                     # no heartbeat for this long: the window is gone. (A minimised window's timers are throttled to about once a minute.)
CREATE_NO_WINDOW = 0x08000000


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]


def version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return ""


def tail(path: Path, lines: int = 80) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def engine_command(base: Path, dry: bool, calibrate: bool = False):
    """The command line of the control engine for this install (the installed exe, or the source tree)."""
    exe = base / "Hexra.exe"
    args = ["--embed", "--engage", "--parent", str(os.getpid())] + (["--dry-run"] if dry else []) + (["--calibrate"] if calibrate else [])
    if getattr(sys, "frozen", False) or exe.exists():
        return [str(exe)] + args
    return [sys.executable, "-m", "hexra", "--rule"] + args


def outside_engines(base: Path):
    """PIDs of Hexra control engines or old-style Hexra windows started from this install that this window did not start."""
    if os.name != "nt":
        return []
    exe = str((base / "Hexra.exe").resolve()).replace("'", "''")
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq '%s' -and $_.ProcessId -ne %d -and "
          "$_.CommandLine -match '--embed|--dry-run|--rule' } | ForEach-Object { $_.ProcessId }" % (exe, os.getpid()))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=15,
                             creationflags=CREATE_NO_WINDOW).stdout
    except Exception:
        return []
    return [int(x) for x in out.split() if x.isdigit()]


class Engine:
    """The control engine process started by this window."""

    def __init__(self, base: Path):
        self.base = base
        self.proc: subprocess.Popen | None = None
        self.dry = False
        self.calibrate = False
        self.started = 0.0
        self.lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, dry: bool, calibrate: bool = False) -> None:
        with self.lock:
            if self.running:
                raise RuntimeError("Hexra is already running")
            (self.base / "data").mkdir(exist_ok=True)
            ipc.clear_all(self.base / "data")
            cmd = engine_command(self.base, dry, True) if calibrate else engine_command(self.base, dry)
            self.proc = subprocess.Popen(cmd, cwd=str(self.base), stdin=subprocess.DEVNULL,
                                         creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.dry, self.calibrate, self.started = dry, calibrate, time.time()

    def toggle(self) -> None:
        if self.running:
            ipc.request(self.base / "data", ipc.TOGGLE)

    def stop(self, wait_s: float = 5.0) -> None:
        with self.lock:
            p = self.proc
            if p is None or p.poll() is not None:
                return
            ipc.request(self.base / "data", ipc.STOP)       # a polite stop first: it lets go of any held mouse button
            try:
                p.wait(timeout=wait_s)
            except subprocess.TimeoutExpired:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
            ipc.clear_all(self.base / "data")

    def status(self) -> dict:
        if not self.running:
            code = None if self.proc is None else self.proc.returncode
            return {"running": False, "exit_code": code, "error": tail(self.base / "data" / "last_error.log", 4) if code else ""}
        st = ipc.read_status(self.base / "data", max_age_s=3.0)
        warming = not st and time.time() - self.started < 20
        return {"running": True, "starting": warming, "dry": self.dry, "calibrating": self.calibrate, **st}


class State:
    def __init__(self, base: Path):
        self.base = base
        self.config = base / "config.yaml"
        self.token = secrets.token_urlsafe(24)
        self.last_seen = time.time()
        self.seen_window = False
        self.stop = threading.Event()
        self.port = 0
        self.engine = Engine(base)
        self.closing_at = 0.0               # the page said it is closing; a heartbeat after this means it was only reloaded

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def show_window(self) -> None:
        """Open the Hexra window, or bring it to the front if it is already open."""
        if not focus_window():
            open_window(self.url())

    def tray_state(self) -> dict:
        st = self.engine.status()
        if not st.get("running"):
            tip = "Hexra: camera off"
        elif st.get("starting"):
            tip = "Hexra: starting"
        elif st.get("dry"):
            tip = "Hexra: try-it mode"
        else:
            tip = "Hexra: controlling" if st.get("engaged") else "Hexra: paused"
        return {"running": st.get("running"), "engaged": st.get("engaged"), "dry": st.get("dry"), "tip": tip}

    def calibration_info(self) -> dict:
        report = None
        try:
            report = json.loads((self.base / "data" / "calibration_report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        return {"exists": (self.base / "data" / "calibration.npz").exists(), "report": report}

    def snapshot(self) -> dict:
        values = config_io.read_values(self.config)
        return {"schema": schema.schema_json(), "values": values, "defaults": schema.defaults(), "version": version(),
                "face_models": (self.base / "models" / "face_recognition_sface_2021dec.onnx").exists(),
                "paths": {"config": str(self.config), "log": str(self.base / "data" / "last_run.log")},
                "autostart": {"available": autostart.available() and (self.base / "Hexra.exe").exists(), "enabled": autostart.is_enabled()},
                "calibration": self.calibration_info(),
                "engine": self.engine.status()}


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HexraApp"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):          # keep the console quiet
            pass

        # -- plumbing
        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in (f"127.0.0.1:{state.port}", f"localhost:{state.port}")

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

        def _authorised(self) -> bool:
            return self._host_ok() and secrets.compare_digest(self.headers.get("X-Hexra-Token", ""), state.token)

        def _stream(self):
            """The live camera picture as a never-ending motion-JPEG, for an <img> in the sidebar."""
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            path, last = state.base / "data" / ipc.PREVIEW, 0.0
            try:
                while not state.stop.is_set():
                    try:
                        m = path.stat().st_mtime
                        data = path.read_bytes() if m != last else None
                    except OSError:
                        m, data = last, None
                    if data:
                        last = m
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(data) + data + b"\r\n")
                        self.wfile.flush()
                    time.sleep(0.04)
            except (BrokenPipeError, ConnectionError, OSError):
                pass
            self.close_connection = True

        # -- routes
        def do_GET(self):
            if not self._host_ok():
                return self._json({"error": "bad host"}, 403)
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/":
                if not secrets.compare_digest(q.get("t", ""), state.token):
                    return self._json({"error": "open this page from the Hexra window"}, 403)
                html = (UI_DIR / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", state.token)
                state.seen_window = True
                state.last_seen = time.time()
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if url.path in ("/app.css", "/app.js", "/fx.js", "/logo.png"):
                f = UI_DIR / url.path[1:]
                if f.exists():
                    ctype = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".png": "image/png"}[f.suffix]
                    return self._send(200, f.read_bytes(), ctype)
                return self._json({"error": "not found"}, 404)
            if url.path == "/preview.mjpg":                       # an <img> cannot send headers, so the token rides in the address
                if not secrets.compare_digest(q.get("t", ""), state.token):
                    return self._json({"error": "not allowed"}, 403)
                state.last_seen = time.time()
                return self._stream()
            if not self._authorised():
                return self._json({"error": "not allowed"}, 403)
            state.last_seen = time.time()
            if url.path == "/api/state":
                return self._json(state.snapshot())
            if url.path == "/api/status":
                return self._json(state.engine.status())
            if url.path == "/api/cameras":
                if state.engine.running:
                    return self._json({"error": "Stop Hexra first: a camera that is in use cannot be listed."}, 409)
                from .camera import probe_cameras
                return self._json({"cameras": probe_cameras()})
            if url.path == "/api/log":
                return self._json({"run": tail(state.base / "data" / "last_run.log"), "error": tail(state.base / "data" / "last_error.log", 30)})
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            url = urlparse(self.path)
            try:                                                   # read the request body FIRST, even for a refused request: leaving it unread
                n = int(self.headers.get("Content-Length", "0") or 0)   # on a keep-alive connection makes Windows reset it under the reply
            except ValueError:
                n = 0
            raw = self.rfile.read(min(n, 200_000)) if n > 0 else b""
            if n > 200_000:
                self.close_connection = True
            if url.path == "/api/closing":                         # sendBeacon cannot set headers, so the token rides in the address
                if self._host_ok() and secrets.compare_digest(parse_qs(url.query).get("t", [""])[0], state.token):
                    state.closing_at = time.time()
                    return self._json({"ok": True})
                return self._json({"error": "not allowed"}, 403)
            if not self._authorised():
                return self._json({"error": "not allowed"}, 403)
            state.last_seen = time.time()
            try:
                body = json.loads(raw or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json({"error": "bad request"}, 400)
            path = urlparse(self.path).path
            try:
                if path == "/api/save":
                    changes = body.get("values")
                    if not isinstance(changes, dict):
                        return self._json({"error": "no values"}, 400)
                    res = config_io.save_values(state.config, changes)
                    return self._json({"ok": True, "saved": res["saved"], "values": config_io.read_values(state.config)})
                if path == "/api/validate":
                    return self._json({"ok": True, "clean": schema.validate_all(body.get("values") or {})})
                if path == "/api/engine/start":
                    dry, restart = bool(body.get("dry")), bool(body.get("restart"))
                    if restart:
                        state.engine.stop()
                    elif state.engine.running:
                        return self._json({"error": "Hexra is already running"}, 409)
                    if outside_engines(state.base):
                        return self._json({"error": "Another Hexra is already running outside this window. Close it first (it would fight over the camera and mouse)."}, 409)
                    state.engine.start(dry)
                    return self._json({"ok": True})
                if path == "/api/calibrate/start":
                    state.engine.stop()
                    if outside_engines(state.base):
                        return self._json({"error": "Another Hexra is already running outside this window. Close it first."}, 409)
                    state.engine.start(True, calibrate=True)
                    return self._json({"ok": True})
                if path == "/api/calibrate/reset":
                    for name in ("calibration.npz", "calibration_report.json"):
                        try:
                            (state.base / "data" / name).unlink()
                        except OSError:
                            pass
                    return self._json({"ok": True, "calibration": state.calibration_info()})
                if path == "/api/engine/stop":
                    state.engine.stop()
                    return self._json({"ok": True})
                if path == "/api/engine/toggle":
                    state.engine.toggle()
                    return self._json({"ok": True})
                if path == "/api/restore-backup":
                    bak = state.config.parent / (state.config.name + ".bak")
                    if not bak.exists():
                        return self._json({"error": "there is no earlier version to go back to"}, 404)
                    shutil.copyfile(bak, state.config)
                    return self._json({"ok": True, "values": config_io.read_values(state.config)})
                if path == "/api/autostart":
                    autostart.set_enabled(bool(body.get("enabled")), state.base / "Hexra.exe")
                    return self._json({"ok": True, "enabled": autostart.is_enabled()})
                if path == "/api/show":
                    state.show_window()
                    return self._json({"ok": True})
                if path == "/api/ping":
                    return self._json({"ok": True})
                if path == "/api/quit":
                    state.stop.set()
                    return self._json({"ok": True})
            except (schema.SettingError, config_io.ConfigError) as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:      # never let one bad request kill the server
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            return self._json({"error": "not found"}, 404)

    return Handler


def _our_windows():
    """Handles of visible top-level windows titled "Hexra" (the app window) that belong to a browser, not to Hexra's own engine."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                cls = ctypes.create_unicode_buffer(64)
                u.GetClassNameW(hwnd, cls, 64)
                if buf.value == "Hexra" and cls.value == "Chrome_WidgetWin_1":
                    found.append(hwnd)
        return True

    u.EnumWindows(each, 0)
    return found


def focus_window() -> bool:
    """Bring an open Hexra window to the front. False if there is none."""
    wins = _our_windows()
    if not wins:
        return False
    import ctypes

    u = ctypes.windll.user32
    u.ShowWindow(wins[0], 9)                       # SW_RESTORE (also un-minimises)
    u.SetForegroundWindow(wins[0])
    return True


def close_windows() -> None:
    import ctypes

    for h in _our_windows():
        ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)       # WM_CLOSE


def open_window(url: str) -> None:
    """Show the page like an application window (Edge/Chrome --app) if one is installed, else in the default browser."""
    candidates = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            candidates += [Path(root) / "Microsoft/Edge/Application/msedge.exe", Path(root) / "Google/Chrome/Application/chrome.exe"]
    for exe in candidates:
        if exe.exists():
            profile = Path(os.environ.get("LOCALAPPDATA", ".")) / "Hexra" / "app-window"
            subprocess.Popen([str(exe), f"--app={url}", "--window-size=1320,900", f"--user-data-dir={profile}", "--no-first-run",
                              "--disable-extensions"], creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
            return
    webbrowser.open(url)


def serve(base: Path | None = None, open_ui: bool = True) -> State:
    state = State(base or app_dir())
    class Server(ThreadingHTTPServer):
        daemon_threads = True
    httpd = Server(("127.0.0.1", 0), make_handler(state))
    state.port = httpd.server_address[1]
    state.httpd = httpd
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if open_ui:
        open_window(f"http://127.0.0.1:{state.port}/?t={state.token}")
    return state


def instance_file() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "Hexra" / "instance.json"


def ask_running_instance(show: bool = True) -> bool:
    """If Hexra is already running (in the tray), tell it to show its window and report True."""
    import urllib.request

    try:
        info = json.loads(instance_file().read_text(encoding="utf-8"))
        if not ipc.process_alive(int(info["pid"])):
            return False
        req = urllib.request.Request(f"http://127.0.0.1:{info['port']}/api/show", data=b"{}", method="POST",
                                     headers={"X-Hexra-Token": info["token"], "Content-Type": "application/json"})
        if not show:
            return True                              # already running, and nothing to show
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    background = "--background" in sys.argv          # started at login: go to the tray, no window
    if ask_running_instance(show=not background):    # Hexra is already running in the tray: just show its window
        return 0
    state = serve(open_ui=False)
    try:
        instance_file().parent.mkdir(parents=True, exist_ok=True)
        instance_file().write_text(json.dumps({"pid": os.getpid(), "port": state.port, "token": state.token}), encoding="utf-8")
    except OSError:
        pass
    tray_icon = None
    if tray_available():
        icon_path = next((p for p in (state.base / "Hexra.ico", state.base / "packaging" / "app.ico") if p.exists()), state.base / "Hexra.ico")

        def start_stop():
            if state.engine.running:
                state.engine.stop()
            elif not outside_engines(state.base):
                state.engine.start(False)

        tray_icon = Tray(icon_path, state.show_window, state.engine.toggle, start_stop, state.stop.set, state.tray_state)
        if not tray_icon.start():
            tray_icon = None
    start = time.time()
    if not (background and tray_icon is not None):   # at login with a tray icon: stay hidden. Without a tray icon the window must show.
        state.show_window()
    try:
        if config_io.read_values(state.config).get("start_control") and not outside_engines(state.base):
            state.engine.start(False)
    except Exception:
        pass
    try:
        while not state.stop.is_set():
            time.sleep(0.5)
            if tray_icon is not None:
                continue                              # in the tray: closing the window never closes Hexra; only "Quit" in the tray does
            # no tray icon could be made: never leave Hexra running with no way to close it, so closing the window ends it
            idle = time.time() - state.last_seen
            if idle > IDLE_QUIT_S and (state.seen_window or time.time() - start > 60):
                break
            if state.closing_at and time.time() - state.closing_at > 4 and state.last_seen <= state.closing_at:
                break
    finally:
        state.engine.stop()                  # quitting stops the engine too, so nothing keeps controlling the mouse unseen
        if tray_icon is not None:
            tray_icon.stop()
        close_windows()
        state.httpd.shutdown()
        try:
            instance_file().unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
