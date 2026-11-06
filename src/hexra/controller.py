"""Pose to screen-action state machine. No camera or OS access here, so it is fully testable."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace

from .filters import OneEuroFilter, PointFilter
from .windows import snap_zone

# feel presets: (min_cutoff, beta, deadzone_px). Measured filter lag at slow/medium hand speeds:
#   smooth ~59/35 ms, balanced ~28/16 ms, responsive ~15/8 ms; steadiness at rest is the reverse.
FEEL = {"smooth": (0.5, 8.0, 5.0), "balanced": (1.0, 25.0, 4.0), "responsive": (1.5, 50.0, 3.0)}

DEFAULT_ACTIONS = {
    "palm": "move", "fist": "move_window", "point": "none",
    "click": "drag", "right": "right_click", "scroll": "scroll",
    "thumb_up": "toggle_maximize", "thumb_down": "minimize", "ell": "close_window",
}
# Window commands: one-shot actions on the window under the cursor, fired after a timed hold (never by a single frame).
COMMANDS = {"toggle_maximize": ("maximise", "toggle_maximize"), "minimize": ("minimise", "minimize"), "close_window": ("close", "close")}
NEUTRAL = "_neutral"   # what the rest of the state machine sees while a command pose is being held: it does nothing
SLOW_ACTIONS = {"drag", "right_click", "scroll", "move_window"}  # have side effects: full debounce
MOVING = ("move", "drag", "move_window")                          # actions that carry the cursor
CURSOR_LANDMARK = 5  # index-finger knuckle: steadier than the fingertip while pinching
KNUCKLES = (5, 9, 13, 17)  # the four finger knuckles: their average is steadier still


def _ramp(speed: float, lo: float = 0.15, hi: float = 0.5) -> float:
    """0 when the hand is nearly still (so tremor is never amplified), 1 once it moves purposefully."""
    return min(max((speed - lo) / (hi - lo), 0.0), 1.0)


@dataclass
class ControllerConfig:
    screen_w: int = 1920                     # size of the area the hand controls (all screens combined by default)
    screen_h: int = 1080
    screen_x: int = 0                        # its top-left corner (negative when a screen sits left of / above the main one)
    screen_y: int = 0
    region: tuple = (0.2, 0.15, 0.8, 0.7)   # active box in the camera frame (x0, y0, x1, y1)
    min_cutoff: float = 1.0                 # lower = steadier hand-tremor rejection (more lag at rest)
    beta: float = 25.0                       # higher = snappier on fast moves
    lead_ms: float = 0.0                    # look-ahead: cancels part of the webcam's built-in delay (0 = off)
    deadzone_px: float = 4.0                # cursor/window ignores movement smaller than this
    release_frames: int = 6                 # frames a click-drag must be gone before it lets go
    grab_release_frames: int = 10           # ...and a grabbed WINDOW (about 0.33 s of a clearly different pose)
    dropout_grace_s: float = 0.3            # keep holding through brief tracking dropouts (motion blur)
    hold_frames: int = 3                    # a pose must persist this many frames to count
    grab_frames: int = 0                    # frames a FIST must persist to grab a window (0 = same as hold_frames)
    cursor_mode: str = "absolute"           # "absolute": the cursor copies your hand position. "relative": mouse-like
    rel_gain_min: float = 1.1               # relative mode: cursor moves this x your hand even when you move slowly
    rel_gain_max: float = 3.0               # ...fast hand = big jumps (acceleration, like a mouse)
    rel_v_low: float = 0.04                 # hand speeds (camera-widths per second) where the gain starts rising...
    rel_v_high: float = 0.8                 # ...and where it reaches the maximum
    rel_softness: float = 0.0003            # per-frame hand motion this small is treated as tremor and mostly ignored
    rel_max_jump: float = 0.2               # a hand "move" bigger than this in ONE frame is a tracking glitch: ignored
    cursor_point: str = "index_knuckle"     # "knuckles": average of the 4 knuckles (steadier). "index_knuckle": one landmark
    click_lookback_s: float = 0.0           # relative mode: a click lands where the cursor was this long ago (0 = off)...
    click_snap_px: float = 100.0            # ...unless the cursor moved more than this since (you were really moving)
    command_hold_s: float = 0.5             # hold thumbs-up / thumbs-down this long to maximise / minimise
    close_hold_s: float = 1.5               # hold the L shape this long to close a window (a ring fills while you hold)
    command_grace_s: float = 0.15           # a command pose may flicker away this long without losing its progress
    command_cooldown_s: float = 0.8         # after a command, a fist cannot grab a window for this long
    grab_move_px: float = 30.0              # a fist only takes hold of a window once the hand has moved this far (0 = at once)
    thumb_guard_s: float = 0.6              # after a thumbs pose, a fist cannot grab a window for this long (a hand relaxing)
    snap_edges: bool = True                 # releasing a fist-dragged window at a screen edge snaps it
    snap_edge_px: float = 30.0              # ...when the cursor is within this many pixels of the edge
    scroll_gain: float = 150.0
    scroll_axis_lock: float = 2.0           # mostly-vertical (or mostly-horizontal) motion scrolls one axis only
    actions: dict = field(default_factory=lambda: dict(DEFAULT_ACTIONS))
    air: dict = field(default_factory=dict)  # options for AirGate (see gate.py)
    camera: dict = field(default_factory=dict)  # {"width": 640, "height": 480}
    face_lock: dict = field(default_factory=dict)  # options for the admin face lock (see face_lock.DEFAULTS)
    attention: dict = field(default_factory=dict)  # options for the attention gate: gestures only while you face the screen (see attention.DEFAULTS)


class Controller:
    def __init__(self, cfg: ControllerConfig, mouse, windows=None):
        from .windows import NullMover

        self.cfg, self.mouse = cfg, mouse
        self.windows = windows or NullMover()
        self._grab = None  # (hand_x, hand_y, win_x, win_y) while a window is held
        self._filter = PointFilter(cfg.min_cutoff, cfg.beta)
        self._scroll_filter = PointFilter(0.8, 1.0)
        self._last_xy = None  # last position actually emitted (for the dead zone)
        self._cursor = None   # relative mode: where the cursor is, in screen pixels
        self._rel_prev = None  # relative mode: (x, y, t) of the previous filtered hand position
        self._raw_prev = None  # relative mode: previous RAW hand position (to spot tracking glitches)
        self._hist = deque()   # (t, x, y) of recent cursor positions, to undo the drift a pinch causes
        self._last_seen = 0.0
        self.note = ""        # why the last drag/grab ended (shown in the app)
        self.hint = ""        # live hint while dragging a window, e.g. "release to snap left" (shown in the app)
        self.cmd_progress = 0.0   # 0..1: how far a held window command (thumbs-up/down, L) is from firing
        self.cmd_label = ""       # ...and which one ("close", "minimise", "maximise")
        self._cmd_pose = None     # the command pose being held, when there is one
        self._cmd_since = 0.0
        self._cmd_seen = 0.0
        self._cmd_fired = False   # a held command fires once; the pose must be left before it can fire again
        self._block_until = 0.0   # a fist cannot grab a window until this time (just after a command)
        self._grab_block_until = 0.0   # ...and until this time (just after a thumbs pose was seen, even if it did not fire)
        self._snap_armed = False   # the cursor has been away from the screen edge since this grab began (so a snap is deliberate)
        self._grab_pending = None  # (x, y) where a fist started, while it has not moved enough yet to take hold of a window
        self.stable = None
        self._cand = None
        self._cand_since = 0.0   # when the current candidate pose first appeared
        self._count = 0
        self._scroll_anchor = (0.0, 0.0)
        self._scroll_rem = [0.0, 0.0]   # fractional wheel steps carried over: [horizontal, vertical]

    @property
    def holding(self) -> bool:
        return self._action(self.stable) in ("drag", "move_window")

    def _action(self, pose):
        return self.cfg.actions.get(pose, "none") if pose else "none"

    def _release(self):
        if self.mouse.is_down:
            self.mouse.release()

    def reset(self):
        self._release()
        self._drop_window()
        self.stable, self._cand, self._count = None, None, 0
        self._filter.reset()
        self._scroll_filter.reset()
        self._last_xy = None
        self._cursor = self._rel_prev = self._raw_prev = None
        self._hist.clear()
        self._clear_command()
        self.hint = ""

    def _clear_command(self):
        self._cmd_pose, self._cmd_fired = None, False
        self.cmd_progress, self.cmd_label = 0.0, ""

    def _command_frame(self, pose, action, t):
        """A window-command pose is on screen this frame: count up, fire once when the hold is complete."""
        if pose != self._cmd_pose:
            self._cmd_pose, self._cmd_since, self._cmd_fired = pose, t, False
        self._cmd_seen = t
        self._grab_block_until = max(self._grab_block_until, t + self.cfg.thumb_guard_s)
        if self._cmd_fired:
            return
        label, method = COMMANDS[action]
        hold = self.cfg.close_hold_s if action == "close_window" else self.cfg.command_hold_s
        self.cmd_label = label
        self.cmd_progress = min((t - self._cmd_since) / max(hold, 1e-6), 1.0)
        if self.cmd_progress >= 1.0:
            self._cmd_fired = True
            result = getattr(self.windows, method)()
            self.note = (f"{result} [{pose}]") if result else f"{label}: no window under the cursor to act on [{pose}]"
            self.cmd_progress, self.cmd_label = 0.0, ""
            self._block_until = t + self.cfg.command_cooldown_s

    def _command_idle(self, t):
        """No command pose this frame. A short flicker keeps the progress; a real change of pose cancels it."""
        if self._cmd_pose is not None and t - self._cmd_seen > self.cfg.command_grace_s:
            self._clear_command()

    def _start_grab(self):
        """The hand has moved with a fist: now (and only now) take hold of the window under the cursor. The window then follows
        the hand from where the fist STARTED, so there is no lag from the first few pixels."""
        ref = self._grab_pending
        self._grab_pending = None
        if ref is None:
            return
        pos = self.windows.grab()
        self._snap_armed = False
        if pos is not None:
            self._grab = (ref[0], ref[1], pos[0], pos[1])

    def _edge(self, x, y):
        rect = self.windows.monitor_rect(x, y) or (self.cfg.screen_x, self.cfg.screen_y, self.cfg.screen_w, self.cfg.screen_h)
        return snap_zone(x, y, rect, self.cfg.snap_edge_px)

    def _snap_on_release(self):
        """A window dragged with a fist and let go at a screen edge: left/right edge = that half, top edge = maximise."""
        if not self.cfg.snap_edges or self._grab is None or not self._snap_armed:
            return                                        # not dragged in from the open screen: a title bar near the top edge is not a snap
        pos = getattr(self.mouse, "position", None) or self._cursor
        if not pos:
            return
        mode = {"left": "left", "right": "right", "top": "maximize"}.get(self._edge(pos[0], pos[1]))
        if mode:
            result = self.windows.snap(mode)
            if result:
                self.note = f"{result} [snap {mode}]"

    def point(self, landmarks):
        """The hand point that drives the cursor (an object with .x and .y)."""
        if self.cfg.cursor_point == "knuckles":
            return SimpleNamespace(x=sum(landmarks[i].x for i in KNUCKLES) / len(KNUCKLES),
                                   y=sum(landmarks[i].y for i in KNUCKLES) / len(KNUCKLES))
        return landmarks[CURSOR_LANDMARK]

    def _snap_target(self, t):
        """Where the cursor was just BEFORE a pinch / three-finger gesture began, so the click lands on what you were
        aiming at, not where the hand drifted while forming the gesture. None if you were genuinely moving."""
        if self.cfg.click_lookback_s <= 0 or self.cfg.cursor_mode != "relative" or not self._hist:
            return None
        want = (self._cand_since or t) - self.cfg.click_lookback_s     # measured from when the gesture first appeared
        sample = next(((x, y) for ts, x, y in self._hist if ts >= want), None)
        if sample is None:
            return None
        _, cx, cy = self._hist[-1]
        if math.hypot(cx - sample[0], cy - sample[1]) > self.cfg.click_snap_px:
            return None
        return sample

    def _drop_window(self):
        self._grab_pending = None
        if self._grab is not None:
            self.windows.release()
            self._grab = None

    def _smooth(self, p, t):
        """Filter the hand position, then lead it slightly along its motion (only when actually moving)."""
        x, y = self._filter(p.x, p.y, t)
        if self.cfg.lead_ms > 0:
            lead = self.cfg.lead_ms / 1000.0
            vx, vy = self._filter.velocity
            x += vx * lead * _ramp(abs(vx))
            y += vy * lead * _ramp(abs(vy))
        return x, y

    def _steady(self, x, y):
        """Dead zone: while your hand only trembles, report the same position instead of jittering."""
        if self._last_xy is not None and math.hypot(x - self._last_xy[0], y - self._last_xy[1]) < self.cfg.deadzone_px:
            return self._last_xy
        self._last_xy = (x, y)
        return self._last_xy

    def _sync_cursor(self):
        """Relative mode: start from wherever the real cursor is now, so taking your hand back to a neutral pose and
        returning (like lifting a mouse) never makes the cursor jump."""
        pos = getattr(self.mouse, "position", None)
        self._cursor = ((float(pos[0]), float(pos[1])) if pos else
                        (self.cfg.screen_x + self.cfg.screen_w / 2.0, self.cfg.screen_y + self.cfg.screen_h / 2.0))
        self._rel_prev = self._raw_prev = None

    def _follow_os_cursor(self):
        """With several screens of different sizes there can be dead areas (no screen there). Windows then places the
        cursor on the nearest screen edge, so adopt where it really is, or the cursor would seem to get stuck."""
        if self.cfg.cursor_mode != "relative" or self._cursor is None:
            return
        pos = getattr(self.mouse, "position", None)
        if pos and math.hypot(pos[0] - self._cursor[0], pos[1] - self._cursor[1]) > 2.0:
            self._cursor = (float(pos[0]), float(pos[1]))

    def _gain(self, speed):
        lo, hi = self.cfg.rel_v_low, self.cfg.rel_v_high
        u = min(max((speed - lo) / max(hi - lo, 1e-9), 0.0), 1.0)
        u = u * u * (3.0 - 2.0 * u)                       # smoothstep: no sudden change in feel
        return self.cfg.rel_gain_min + (self.cfg.rel_gain_max - self.cfg.rel_gain_min) * u

    def _cursor_target(self, p, t):
        """Where the cursor (or a grabbed window) should be, in screen pixels."""
        relative = self.cfg.cursor_mode == "relative"
        if relative:
            if self._cursor is None:
                self._sync_cursor()
            jump = self._raw_prev is not None and math.hypot(p.x - self._raw_prev[0], p.y - self._raw_prev[1]) > self.cfg.rel_max_jump
            self._raw_prev = (p.x, p.y)
            if jump:                                  # the tracker snapped to a different spot: re-anchor, never fling the cursor
                self._filter.reset()
                self._rel_prev = None
                return self._cursor
        x, y = self._smooth(p, t)
        if not relative:
            return self._steady(*self._map(x, y))
        if self._rel_prev is None:
            self._rel_prev = (x, y, t)
            return self._cursor
        px, py, pt = self._rel_prev
        self._rel_prev = (x, y, t)
        dt = t - pt
        dx, dy = x - px, y - py
        mag = math.hypot(dx, dy)
        if dt <= 0 or mag == 0:
            return self._cursor
        factor = self._gain(mag / dt) * (mag / (mag + self.cfg.rel_softness))   # accelerate, but damp tremor
        x0, y0, x1, y1 = self.cfg.region
        cx = self._cursor[0] + dx * (self.cfg.screen_w / (x1 - x0)) * factor
        cy = self._cursor[1] + dy * (self.cfg.screen_h / (y1 - y0)) * factor
        left, top = float(self.cfg.screen_x), float(self.cfg.screen_y)
        self._cursor = (min(max(cx, left), left + self.cfg.screen_w - 1.0), min(max(cy, top), top + self.cfg.screen_h - 1.0))
        return self._cursor

    def _map(self, x, y):
        x0, y0, x1, y1 = self.cfg.region
        u = min(max((x - x0) / (x1 - x0), 0.0), 1.0)
        v = min(max((y - y0) / (y1 - y0), 0.0), 1.0)
        return self.cfg.screen_x + u * (self.cfg.screen_w - 1), self.cfg.screen_y + v * (self.cfg.screen_h - 1)

    def step(self, pose, landmarks, t, engaged=True):
        """Process one frame. pose None means no hand. Returns the stable (debounced) pose."""
        if not engaged:
            if self.holding:
                self.note = "released: control paused"
            self.reset()
            return None
        if pose is None or landmarks is None:
            if self.holding and t - self._last_seen <= self.cfg.dropout_grace_s:
                return self.stable                  # brief dropout: keep holding, do nothing this frame
            if self.holding:
                self.note = "released: hand lost / left the air zone"
            self.reset()
            return None
        self._last_seen = t
        act_pose = self._action(pose)
        shown = None
        if act_pose in COMMANDS and self._action(self.stable) == "move_window":
            if self._grab is None:
                self._grab_pending = None                # no window is held yet (the hand has not moved): that fist was on its way
                self.stable = NEUTRAL                    # to a thumbs pose, so nothing was grabbed and there is nothing to undo
            else:
                pose, act_pose = self.stable, "move_window"   # a thumb popping out of a window you are really dragging: ignored
        if act_pose in COMMANDS and not self.holding and t >= self._block_until:
            self._command_frame(pose, act_pose, t)      # thumbs-up / thumbs-down / L: a timed one-shot command
            shown, pose = pose, NEUTRAL                  # ...and the cursor, scroll and clicks do nothing meanwhile
            if self.stable != NEUTRAL:                   # stop at once: the hand is no longer steering the cursor
                self._enter(NEUTRAL, landmarks, t)
                self.stable = NEUTRAL
        elif ((act_pose in COMMANDS and t < self._block_until)
              or (act_pose == "move_window" and t < max(self._block_until, self._grab_block_until))) and not self.holding:
            if pose == self._cmd_pose:
                self._cmd_seen = t                       # still holding the pose that just fired: it stays "already fired"
            else:
                self._command_idle(t)
            pose = NEUTRAL                               # just after a command: no accidental window grab or repeat
        else:
            self._command_idle(t)
        if pose == self._cand:
            self._count += 1
        else:
            self._cand, self._count, self._cand_since = pose, 1, t
        # Side-effect actions (click, right-click, scroll, window grab) need the full hold. Moving the cursor
        # and neutral poses switch after 2 frames, so the cursor reacts quickly without risking a stray click.
        need = self.cfg.hold_frames if self._action(pose) in SLOW_ACTIONS else min(2, self.cfg.hold_frames)
        if self._action(pose) == "move_window" and self.cfg.grab_frames:
            need = max(need, self.cfg.grab_frames)       # grabbing a window needs a longer, deliberate hold
        if self.holding and pose != self.stable:
            held = self.cfg.grab_release_frames if self._action(self.stable) == "move_window" else self.cfg.release_frames
            need = max(need, held)                       # letting go needs a clear, sustained change
        # A hand that just appeared may start moving the cursor at once, but a click-type action (click, right-click,
        # scroll, window grab) always waits for its full hold, even when it is the very first pose seen.
        first_and_harmless = self.stable is None and self._action(pose) not in SLOW_ACTIONS
        if pose != self.stable and (self._count >= need or first_and_harmless):
            self._enter(pose, landmarks, t)
            self.stable = pose
        p = self.point(landmarks)
        act = self._action(self.stable)
        if act in ("move", "drag"):
            target = self._cursor_target(p, t)
            self.mouse.move(*target)
            self._follow_os_cursor()
            if act == "move":
                self._hist.append((t, target[0], target[1]))
                while self._hist and t - self._hist[0][0] > 1.0:
                    self._hist.popleft()
        elif act == "move_window":
            hx, hy = self._cursor_target(p, t)
            self.mouse.move(hx, hy)  # the cursor stays on the window it is dragging
            self._follow_os_cursor()
            if self._grab is None and self._grab_pending is not None:
                if math.hypot(hx - self._grab_pending[0], hy - self._grab_pending[1]) >= self.cfg.grab_move_px:
                    self._start_grab()
            if self._grab is not None:
                gx, gy, wx, wy = self._grab
                self.windows.move_to(wx + hx - gx, wy + hy - gy)
                zone = self._edge(hx, hy) if self.cfg.snap_edges else None
                if zone is None:
                    self._snap_armed = True
                elif not self._snap_armed:
                    zone = None                          # it started at the edge and has not left it: no hint, no snap
                self.hint = {"left": "release to snap left", "right": "release to snap right", "top": "release to maximise"}.get(zone, "")
        elif act == "scroll":
            x, y = self._scroll_filter(p.x, p.y, t)
            dx = x - self._scroll_anchor[0]       # hand right gives positive
            dy = self._scroll_anchor[1] - y       # hand up gives positive
            self._scroll_anchor = (x, y)
            lock = self.cfg.scroll_axis_lock
            if abs(dx) > lock * abs(dy):
                dy = 0.0                           # clearly sideways: ignore the vertical wobble
            elif abs(dy) > lock * abs(dx):
                dx = 0.0                           # clearly up/down: ignore the sideways wobble
            self._scroll_rem[0] += dx * self.cfg.scroll_gain
            self._scroll_rem[1] += dy * self.cfg.scroll_gain
            for axis, send in ((0, self.mouse.hscroll), (1, self.mouse.scroll)):
                steps = int(self._scroll_rem[axis])
                if steps:
                    send(steps)
                    self._scroll_rem[axis] -= steps
        if act != "move_window":
            self.hint = ""
        return shown or self.stable

    def _enter(self, pose, landmarks, t=0.0):
        old, new = self._action(self.stable), self._action(pose)
        if old in ("drag", "move_window") and new != old:
            self.note = f"released: pose changed to {pose}"
        if old == "drag" and new != "drag":
            self._release()
        if old == "move_window" and new != "move_window":
            self._snap_on_release()
            self._drop_window()
        if new == "move_window":
            if old not in MOVING:
                self._cursor = None                      # resync from the real cursor (relative mode)
            p = self.point(landmarks)
            self._filter.reset()
            self._last_xy = None
            if self.cfg.cursor_mode == "relative":
                if self._cursor is None:
                    self._sync_cursor()
                hx, hy = self._cursor
            else:
                hx, hy = self._map(p.x, p.y)
            self._grab_pending = (hx, hy)
            if self.cfg.grab_move_px <= 0:
                self._start_grab()                       # take hold at once (the old behaviour)
        if old in ("none", "scroll", "right_click", "move_window") and new in ("move", "drag"):
            self._filter.reset()  # no smoothing lag from a stale position
            self._last_xy = None
        if new in MOVING and old not in MOVING:
            self._cursor = self._rel_prev = self._raw_prev = None   # relative mode: start from the real cursor, no jump
            self._hist.clear()
        if new in ("drag", "right_click"):
            snap = self._snap_target(t)
            if snap is not None and self._cursor is not None:
                self._cursor = snap                       # click where you were aiming, before the gesture moved your hand
                self.mouse.move(*snap)
                self._last_xy = snap
        if new == "drag":
            if self.cfg.cursor_mode != "relative":       # absolute: click where the hand is. relative: where the cursor is
                p = self.point(landmarks)
                self.mouse.move(*self._map(p.x, p.y))
            self.mouse.press()
        elif new == "right_click":
            self.mouse.click_right()
        elif new == "scroll":
            self._scroll_filter.reset()
            q = self.point(landmarks)
            self._scroll_anchor = self._scroll_filter(q.x, q.y, 0.0)
            self._scroll_rem = [0.0, 0.0]
