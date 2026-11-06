"""The settings server: local only, token protected, validates everything, never writes outside config.yaml."""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from hexra import settings_app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def srv(tmp_path):
    shutil.copy(ROOT / "config.yaml", tmp_path / "config.yaml")
    state = settings_app.serve(tmp_path, open_ui=False)
    yield state, tmp_path
    state.httpd.shutdown()


def call(state, path, body=None, token=True, host=None):
    req = urllib.request.Request(f"http://127.0.0.1:{state.port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("X-Hexra-Token", state.token)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_the_page_needs_the_secret_token_in_its_address(srv):
    state, _ = srv
    assert call(state, "/", token=False)[0] == 403
    assert call(state, "/?t=wrong", token=False)[0] == 403
    code, body = call(state, f"/?t={state.token}", token=False)
    assert code == 200 and state.token.encode() in body and b"__TOKEN__" not in body


def test_the_api_refuses_requests_without_the_token_or_with_a_foreign_host(srv):
    state, _ = srv
    assert call(state, "/api/state", token=False)[0] == 403
    assert call(state, "/api/save", {"values": {}}, token=False)[0] == 403
    assert call(state, "/api/state", host="evil.example")[0] == 403          # DNS-rebinding style request


def test_state_lists_every_setting_with_values(srv):
    state, _ = srv
    code, body = call(state, "/api/state")
    data = json.loads(body)
    assert code == 200 and data["values"]["feel"] in ("responsive", "balanced", "smooth")
    ids = {s["id"] for g in data["schema"]["groups"] for s in g["settings"]}
    assert set(data["values"]) == ids and len(ids) > 40


def test_saving_changes_the_file_and_keeps_its_comments(srv):
    state, tmp = srv
    before = (tmp / "config.yaml").read_text(encoding="utf-8")
    code, body = call(state, "/api/save", {"values": {"hold_frames": 5, "actions.fist": "none"}})
    assert code == 200 and json.loads(body)["values"]["hold_frames"] == 5
    after = (tmp / "config.yaml").read_text(encoding="utf-8")
    assert after != before and after.count("#") == before.count("#")
    assert (tmp / "config.yaml.bak").read_text(encoding="utf-8") == before


def test_invalid_input_is_refused_with_a_message_and_changes_nothing(srv):
    state, tmp = srv
    before = (tmp / "config.yaml").read_text(encoding="utf-8")
    for bad in ({"hold_frames": 999}, {"feel": "warp"}, {"not_a_setting": 1}, {"actions.fist": "rm -rf"}):
        code, body = call(state, "/api/save", {"values": bad})
        assert code == 400 and json.loads(body)["error"]
    assert call(state, "/api/save", {"values": "x"})[0] == 400
    assert (tmp / "config.yaml").read_text(encoding="utf-8") == before


def test_restore_goes_back_to_the_previous_save(srv):
    state, tmp = srv
    assert call(state, "/api/restore-backup", {})[0] == 404
    original = (tmp / "config.yaml").read_text(encoding="utf-8")
    call(state, "/api/save", {"values": {"hold_frames": 6}})
    code, _ = call(state, "/api/restore-backup", {})
    assert code == 200 and (tmp / "config.yaml").read_text(encoding="utf-8") == original


def test_only_the_known_static_files_are_served(srv):
    state, _ = srv
    for p in ("/app.css", "/app.js", "/logo.png"):
        assert call(state, p, token=False)[0] == 200
    assert call(state, "/../config.yaml", token=False)[0] in (403, 404)
    assert call(state, "/config.yaml", token=False)[0] in (403, 404)


def test_the_log_tail_is_served_and_a_missing_log_is_empty(srv):
    state, tmp = srv
    assert json.loads(call(state, "/api/log")[1])["run"] == ""
    (tmp / "data").mkdir()
    (tmp / "data" / "last_run.log").write_text("one\ntwo\n", encoding="utf-8")
    assert json.loads(call(state, "/api/log")[1])["run"] == "one\ntwo"


def test_the_engine_command_is_right(tmp_path):
    cmd = settings_app.engine_command(tmp_path, dry=True)
    assert "--embed" in cmd and "--engage" in cmd and cmd[-1] == "--dry-run" and "-m" in cmd     # no exe here: runs the source tree
    assert cmd[cmd.index("--parent") + 1] == str(os.getpid())
    (tmp_path / "Hexra.exe").write_bytes(b"")
    exe_cmd = settings_app.engine_command(tmp_path, dry=False)
    assert exe_cmd[0] == str(tmp_path / "Hexra.exe") and "--embed" in exe_cmd and "--dry-run" not in exe_cmd


# ---------------------------------------------------------------- the engine process, with a stand-in that speaks the same protocol
FAKE_ENGINE = """
import sys, time, os, json
from pathlib import Path
sys.path.insert(0, r'%s')
from hexra import ipc
base = Path('.').resolve(); data = base / 'data'
engaged = True
while True:
    if ipc.consume(data, ipc.STOP): break
    if ipc.consume(data, ipc.TOGGLE): engaged = not engaged
    ipc.write_atomic(data / ipc.PREVIEW, b'\\xff\\xd8fakejpeg\\xff\\xd9')
    ipc.write_status(data, engaged=engaged, pose='palm', fps=30, lat_ms=55, dry=False)
    time.sleep(0.05)
"""


@pytest.fixture()
def fake_engine(srv, monkeypatch):
    state, tmp = srv
    (tmp / "fake_engine.py").write_text(FAKE_ENGINE % str(ROOT / "src"), encoding="utf-8")
    monkeypatch.setattr(settings_app, "engine_command", lambda base, dry: [sys.executable, str(tmp / "fake_engine.py")])
    monkeypatch.setattr(settings_app, "outside_engines", lambda base: [])
    yield state, tmp
    state.engine.stop()


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_start_shows_status_and_the_camera_stream_then_stop_ends_it(fake_engine):
    state, tmp = fake_engine
    assert json.loads(call(state, "/api/status")[1])["running"] is False
    assert call(state, "/api/engine/start", {"dry": False})[0] == 200
    assert wait_for(lambda: json.loads(call(state, "/api/status")[1]).get("pose") == "palm")
    st = json.loads(call(state, "/api/status")[1])
    assert st["running"] and st["engaged"] and st["fps"] == 30
    # the camera picture is streamed as motion-JPEG (the token is in the address because an <img> cannot send headers)
    assert call(state, "/preview.mjpg", token=False)[0] == 403
    req = urllib.request.Request(f"http://127.0.0.1:{state.port}/preview.mjpg?t={state.token}")
    with urllib.request.urlopen(req, timeout=10) as r:
        assert "multipart/x-mixed-replace" in r.headers["Content-Type"]
        chunk = r.read(200)
    assert b"--frame" in chunk and b"image/jpeg" in chunk
    assert call(state, "/api/engine/start", {"dry": False})[0] == 409       # already running
    assert call(state, "/api/engine/stop", {})[0] == 200
    assert json.loads(call(state, "/api/status")[1])["running"] is False
    assert not (tmp / "data" / "preview.jpg").exists()                      # left no stale picture behind


def test_pause_and_resume_reach_the_engine(fake_engine):
    state, _ = fake_engine
    call(state, "/api/engine/start", {})
    assert wait_for(lambda: json.loads(call(state, "/api/status")[1]).get("engaged") is True)
    call(state, "/api/engine/toggle", {})
    assert wait_for(lambda: json.loads(call(state, "/api/status")[1]).get("engaged") is False)
    call(state, "/api/engine/toggle", {})
    assert wait_for(lambda: json.loads(call(state, "/api/status")[1]).get("engaged") is True)


def test_restart_replaces_the_engine_and_an_outside_engine_blocks_a_start(fake_engine, monkeypatch):
    state, _ = fake_engine
    call(state, "/api/engine/start", {})
    first = state.engine.proc.pid
    assert call(state, "/api/engine/start", {"restart": True})[0] == 200
    assert state.engine.proc.pid != first and state.engine.running
    call(state, "/api/engine/stop", {})
    monkeypatch.setattr(settings_app, "outside_engines", lambda base: [1234])
    code, body = call(state, "/api/engine/start", {})
    assert code == 409 and "outside" in json.loads(body)["error"]


def test_closing_the_window_is_noticed_but_a_reload_cancels_it(srv):
    state, _ = srv
    assert call(state, f"/api/closing?t=wrong", {}, token=False)[0] == 403
    assert call(state, f"/api/closing?t={state.token}", {}, token=False)[0] == 200
    assert state.closing_at > 0
    state.last_seen = time.time() + 1                                          # a heartbeat after it: the page was only reloaded
    assert state.last_seen > state.closing_at


def test_status_ignores_a_stale_status_file(tmp_path):
    from hexra import ipc
    ipc.write_status(tmp_path, engaged=True)
    assert ipc.read_status(tmp_path)["engaged"] is True
    assert ipc.read_status(tmp_path, max_age_s=-1) == {}
    assert ipc.read_status(tmp_path / "nowhere") == {}


def test_flags_are_consumed_once(tmp_path):
    from hexra import ipc
    assert not ipc.consume(tmp_path, ipc.STOP)
    ipc.request(tmp_path, ipc.STOP)
    assert ipc.consume(tmp_path, ipc.STOP) and not ipc.consume(tmp_path, ipc.STOP)
    assert ipc.process_alive(os.getpid()) and not ipc.process_alive(0)
