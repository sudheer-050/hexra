"""Main loop: webcam -> hand landmarks -> pose -> screen action.

F8 engages/pauses control, F9 quits (or click the camera window: e = toggle, q = quit).
--dry-run tracks and shows poses without touching your mouse. --rule uses the rule-based recogniser.
Messages are also written to data/last_run.log, so you can read what happened after the window closes.
"""
from __future__ import annotations

import argparse
import logging
import threading
import time
from pathlib import Path

import cv2

from .actions import NullMouse, PynputMouse
from .attention import build as build_attention
from .calibrate import draw_hand
from .camera import ThreadedCamera
from .multicam import MultiSource
from .controller import FEEL, Controller, ControllerConfig
from . import ipc
from .display import Display, FilePreview
from .face_lock import DEFAULTS as FACE_LOCK_DEFAULTS
from . import icon
from .features import normalize
from .gate import AirGate
from .poses import MLRecognizer, RuleRecognizer
from .screen import enable_dpi_awareness, list_monitors, screen_rect
from .tracker import HandTracker, ensure_model
from .windows import NullMover, make_mover

log = logging.getLogger("hexra")


def load_config(path: str) -> ControllerConfig:
    cfg = ControllerConfig()
    p = Path(path)
    if not p.exists():
        return cfg
    import yaml

    data = yaml.safe_load(p.read_text(encoding="utf-8-sig")) or {}
    scr = data.get("screen", {})
    cfg.screen_x, cfg.screen_y, cfg.screen_w, cfg.screen_h = screen_rect(
        scr.get("span", "all"), scr.get("monitor"), manual=(scr.get("width"), scr.get("height"), scr.get("left"), scr.get("top")))
    if "region" in data:
        cfg.region = tuple(data["region"])
    feel = str(data.get("feel", "balanced")).lower()
    if feel not in FEEL:
        raise SystemExit(f"config.yaml: feel must be one of {sorted(FEEL)}, not {feel!r}")
    cfg.min_cutoff, cfg.beta, cfg.deadzone_px = FEEL[feel]
    mode = str(data.get("cursor_mode", "absolute")).lower()
    if mode not in ("absolute", "relative"):
        raise SystemExit(f"config.yaml: cursor_mode must be 'absolute' or 'relative', not {mode!r}")
    cfg.cursor_mode = mode
    point = str(data.get("cursor_point", "index_knuckle")).lower()
    if point not in ("index_knuckle", "knuckles"):
        raise SystemExit(f"config.yaml: cursor_point must be 'knuckles' or 'index_knuckle', not {point!r}")
    cfg.cursor_point = point
    for key in ("min_cutoff", "beta", "deadzone_px", "lead_ms", "hold_frames", "grab_frames", "release_frames", "grab_release_frames", "dropout_grace_s",
                "scroll_gain", "scroll_axis_lock", "rel_gain_min", "rel_gain_max", "rel_v_low", "rel_v_high",
                "rel_softness", "rel_max_jump", "click_lookback_s", "click_snap_px",
                "command_hold_s", "close_hold_s", "command_grace_s", "command_cooldown_s", "snap_edges", "snap_edge_px",
                "grab_move_px", "thumb_guard_s"):
        if key in data:
            setattr(cfg, key, type(getattr(cfg, key))(data[key]))
    cfg.actions.update(data.get("actions", {}))
    cfg.air = dict(data.get("air", {}))
    cfg.camera = dict(data.get("camera", {}))
    cfg.face_lock = dict(data.get("face_lock", {}))
    cfg.attention = dict(data.get("attention", {}))
    return cfg


def _start_hotkeys(on_toggle, on_quit):
    try:
        from pynput import keyboard

        listener = keyboard.GlobalHotKeys({"<f8>": on_toggle, "<f9>": on_quit})
        listener.start()
        return listener
    except Exception as exc:
        log.warning("Global hotkeys unavailable (%s). Use the camera window: e = toggle, q = quit.", exc)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(prog="hexra")
    ap.add_argument("--dry-run", action="store_true", help="track and show poses, never move the mouse")
    ap.add_argument("--rule", action="store_true", help="use the rule-based recogniser (no training needed)")
    ap.add_argument("--no-face-lock", action="store_true", help="run without the admin face lock this time")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--embed", action="store_true", help="run as the engine of the Hexra app: the picture goes to the app window, not a window of its own")
    ap.add_argument("--engage", action="store_true", help="start with control engaged (the app's Start button)")
    ap.add_argument("--parent", type=int, default=0, help="quit when this process (the app window) is gone")
    args = ap.parse_args()
    Path("data").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True,
                        handlers=[logging.StreamHandler(), logging.FileHandler("data/last_run.log", mode="w", encoding="utf-8")])

    enable_dpi_awareness()
    icon.set_app_id()                                  # the taskbar shows Hexra's icon, not Python's
    icon.apply_to_console()
    cfg = load_config(args.config)
    if not Path(args.config).exists():
        cfg.screen_x, cfg.screen_y, cfg.screen_w, cfg.screen_h = screen_rect()
    n_screens = len(list_monitors())
    log.info("Controlling %s: %dx%d, top-left at (%d, %d)", f"{n_screens} screens" if n_screens > 1 else "the screen",
             cfg.screen_w, cfg.screen_h, cfg.screen_x, cfg.screen_y)

    model_path = Path("models/pose_classifier.joblib")
    if args.rule or not model_path.exists():
        recog, name = RuleRecognizer(), "rule-based"
        if not args.rule:
            log.info("No trained model yet (run calibrate, then train). Using the rule-based recogniser.")
    else:
        recog, name = MLRecognizer.load(str(model_path)), "trained"
    log.info("Recogniser: %s", name)

    lock = None
    lock_opts = {**FACE_LOCK_DEFAULTS, **cfg.face_lock}
    if lock_opts["enabled"] and not args.no_face_lock:
        from .enroll_face import build_face_lock          # (enrols the admin first if nobody is enrolled yet)

        lock = build_face_lock(lock_opts)
        log.info("Face lock ON: gestures work only while the enrolled admin face is recognised.")
    else:
        log.info("Face lock OFF: anyone can use the gestures.")

    cam_indices = [int(i) for i in (cfg.camera.get("use") or [0])][:2]
    multi = len(cam_indices) >= 2
    attention = None if multi else build_attention(cfg.attention)
    if multi and cfg.attention.get("enabled"):
        log.info("Two cameras: the face-direction gate is switched off (it needs one camera that faces you).")
    if attention is not None:
        log.info("Attention gate ON: gestures work only while you face the screen (head turned less than %d degrees).",
                 attention.gate.max_turn_deg)

    mouse = NullMouse() if args.dry_run else PynputMouse()
    gate = AirGate(**cfg.air)
    ctl = Controller(cfg, mouse, NullMover() if args.dry_run else make_mover())
    cam_w, cam_h = int(cfg.camera.get("width", 640)), int(cfg.camera.get("height", 480))
    model = ensure_model("models/hand_landmarker.task")
    msrc = None
    if multi:
        caps = [ThreadedCamera(i, cam_w, cam_h) for i in cam_indices]
        bad = [i for i, c in zip(cam_indices, caps) if not c.opened]
        if bad:
            for c in caps:
                c.release()
            raise SystemExit(f"Could not open camera {', '.join(str(i) for i in bad)}. Check it is plugged in and not used by another program, "
                             "or choose different cameras on the Camera page.")
        msrc = MultiSource([(c, HandTracker(model)) for c in caps])
        tracker = cap = None
        log.info("Two cameras (%s): both track your hand; the better view gives the pose and both steady the cursor.",
                 " + ".join(f"camera {i}" for i in cam_indices))
    else:
        tracker = HandTracker(model)
        cap = ThreadedCamera(cam_indices[0], cam_w, cam_h)
        if not cap.opened:
            raise SystemExit("Could not open the webcam.")

    engaged, stop = threading.Event(), threading.Event()
    if args.dry_run or args.engage:
        engaged.set()

    def toggle():
        engaged.clear() if engaged.is_set() else engaged.set()
        log.info("Control %s", "ENGAGED" if engaged.is_set() else "PAUSED")

    listener = _start_hotkeys(toggle, stop.set)
    base = Path("data").resolve()                       # where the app window and the engine leave each other files (ipc.py)
    # the preview runs on its own thread: drawing must never delay the cursor
    display = FilePreview(base) if args.embed else Display("Hexra")
    if args.embed:
        ipc.clear_all(base)
    log.info("Ready. %s F9 quits.", "Dry run: mouse is NOT controlled." if args.dry_run else "Press F8 to engage.")

    fps_t, fps, fps_n, lat_ms = time.monotonic(), 0.0, 0, 0.0
    shown_note, note_until = "", 0.0
    was_away = False
    next_ctl = next_status = 0.0
    try:
        while not stop.is_set():
            if args.embed and time.monotonic() >= next_ctl:        # the app window's requests, five times a second
                next_ctl = time.monotonic() + 0.2
                if ipc.consume(base, ipc.STOP) or (args.parent and not ipc.process_alive(args.parent)):
                    log.info("Stopped by the Hexra window.")
                    break
                if ipc.consume(base, ipc.TOGGLE):
                    toggle()
            inset, cams_mode = [], ""
            if multi:
                step_in = msrc.read()
                if step_in is None:
                    if not msrc.alive:
                        log.error("The cameras stopped delivering frames.")
                        break
                    continue
                frame, t, det, inset, cams_mode = step_in.frame, step_in.t, step_in.det, step_in.inset, step_in.mode
            else:
                got = cap.read()
                if got is None:
                    if not cap.alive:
                        log.error("Camera stopped delivering frames.")
                        break
                    continue
                frame, t = got                       # t = the moment the camera captured this frame
                frame = cv2.flip(frame, 1)
                det = tracker.detect(frame, int(t * 1000))
            pose, lm = None, None
            if det:
                lm = det[0]
                try:
                    pose = recog.predict_features(normalize(lm, det[1]))     # finger shape: from the camera with the better view
                except ValueError:
                    pose = None
                if multi:
                    lm = det[2]                                              # position: the fused hand, in camera 1's frame
            if lock is not None:
                lock.submit(frame, t)                     # a background thread checks the picture; this never waits
                if not lock.allowed(t):
                    lm = pose = None                      # not the admin: the hand is ignored
            looking_away = False
            if attention is not None:
                attention.submit(frame, t)                # a background thread checks the picture; this never waits
                looking_away = not attention.allowed(t)
                if looking_away != was_away:
                    log.info("Looking away: gestures paused" if looking_away else "Facing the screen again: gestures on")
                    was_away = looking_away
                if looking_away:
                    lm = pose = None                      # you are not looking at the screen: the hand is ignored
            active = gate.update(lm, pose, t, holding=ctl.holding)
            stable = ctl.step(pose if active else None, lm if active else None, t, engaged.is_set())
            if ctl.note:
                log.info(ctl.note)
                shown_note, note_until = ctl.note, time.monotonic() + 3.0
                ctl.note = ""
            lat_ms = 0.9 * lat_ms + 0.1 * (time.monotonic() - t) * 1000   # capture -> action sent (before drawing)

            fps_n += 1
            now_m = time.monotonic()
            if now_m - fps_t >= 1.0:                      # frames counted over a second of real time (camera timestamps can repeat)
                fps, fps_n, fps_t = fps_n / (now_m - fps_t), 0, now_m
            h, w = frame.shape[:2]
            x0, y0, x1, y1 = cfg.region
            cv2.rectangle(frame, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), (0, 255, 255), 1)
            if lm:
                draw_hand(frame, lm)
                p = ctl.point(lm)
                cv2.circle(frame, (int(p.x * w), int(p.y * h)), 10, (0, 0, 255) if stable == "click" else (0, 255, 0), 2)
                if ctl.cmd_progress > 0:                          # a held window command: a ring fills until it fires
                    centre = (int(p.x * w), int(p.y * h))
                    colour = (0, 0, 255) if ctl.cmd_label == "close" else (0, 200, 255)
                    cv2.ellipse(frame, centre, (34, 34), -90, 0, 360 * ctl.cmd_progress, colour, 5, cv2.LINE_AA)
                    cv2.putText(frame, f"hold to {ctl.cmd_label}", (max(centre[0] - 70, 4), max(centre[1] - 48, 18)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2, cv2.LINE_AA)
            if gate.enabled:
                ly = int(gate.max_center_y * h)
                cv2.line(frame, (0, ly), (w, ly), (255, 128, 0), 1)   # hand must be ABOVE this line
                if not gate.awake:
                    msg = "ASLEEP: raise an open palm in the air for 1s to wake"
                    if gate.wake_progress > 0:
                        msg = f"WAKING... {gate.wake_progress:.0%}"
                    cv2.putText(frame, msg, (10, h - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                elif not active:
                    cv2.putText(frame, "hand not in the air - ignored", (10, h - 45), cv2.FONT_HERSHEY_SIMPLEX,
                                0.7, (0, 165, 255), 2)
            if lock is not None:
                ok_now = lock.allowed(t)
                cv2.putText(frame, lock.describe(t), (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 0) if ok_now else (0, 0, 255), 1, cv2.LINE_AA)
                if not ok_now:
                    cv2.putText(frame, "LOCKED", (10, h - 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
            if attention is not None:
                cv2.putText(frame, attention.describe(t), (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 165, 255) if looking_away else (0, 255, 0), 1, cv2.LINE_AA)
                if looking_away:
                    cv2.putText(frame, "LOOKING AWAY - paused", (10, h - 160), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 165, 255), 3, cv2.LINE_AA)
            if ctl.hint:
                cv2.putText(frame, ctl.hint.upper(), (10, h - 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            if shown_note and time.monotonic() < note_until:
                cv2.putText(frame, shown_note, (10, h - 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
            status = "ENGAGED" if engaged.is_set() else "PAUSED (F8 or 'e')"
            cv2.putText(frame, f"{status}   pose: {stable or '-'}   [{name}]   {fps:.0f} fps  {lat_ms:.0f} ms", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if engaged.is_set() else (0, 0, 255), 2)
            if inset:                                                   # the other camera, as a small picture in the corner
                other, other_lm = inset[0]
                other = other.copy()
                if other_lm:
                    draw_hand(other, other_lm)
                tw = frame.shape[1] // 3
                th = int(other.shape[0] * tw / other.shape[1])
                small = cv2.resize(other, (tw, th))
                cv2.rectangle(small, (0, 0), (tw - 1, th - 1), (255, 255, 255), 1)
                frame[frame.shape[0] - th - 4:frame.shape[0] - 4, frame.shape[1] - tw - 4:frame.shape[1] - 4] = small
            if multi:
                cv2.putText(frame, f"2 cameras: {cams_mode}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
            display.show(frame)
            if args.embed and time.monotonic() >= next_status:
                next_status = time.monotonic() + 0.25
                ipc.write_status(base, engaged=engaged.is_set(), pose=stable or "", fps=round(min(fps, 240)), lat_ms=round(lat_ms), dry=bool(args.dry_run),
                                 asleep=bool(gate.enabled and not gate.awake), away=looking_away, note=shown_note if time.monotonic() < note_until else "",
                                 hint=ctl.hint or "", cams=cams_mode)
            quit_now = False
            for key in display.keys():
                if key == ord("q"):
                    quit_now = True
                elif key == ord("e"):
                    toggle()
            if quit_now:
                break
    finally:
        ctl.reset()
        display.close()
        if lock is not None:
            lock.close()
        if attention is not None:
            attention.close()
        if multi:
            msrc.release()
        else:
            cap.release()
            tracker.close()
        cv2.destroyAllWindows()
        if listener:
            listener.stop()
        if args.embed:
            ipc.clear_all(base)


if __name__ == "__main__":
    main()
