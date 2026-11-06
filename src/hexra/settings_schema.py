"""Every Hexra setting in one place: its type, range, default, a plain-language explanation and what it does to latency.

The settings app (settings_app.py + ui/) is built from this list, and the server uses it to validate everything it saves, so
a setting that is not listed here can never be written. Defaults are the values shipped in config.yaml.

Latency notes ("impact") come in four kinds:
  frames   the value is a number of camera frames in a row; the delay is  value x frame time  (33 ms at 30 fps)
  seconds  the value is a time; the delay is the value itself
  options  every choice carries its own number and tone (see Option)
  note     a sentence, with a tone: good / neutral / warn
  none     no effect on latency
and a basis: how the number was obtained (measured, simulation, calculated, estimate), shown to the user honestly.
"""
from __future__ import annotations

FPS = 30.0                      # the camera's real frame rate on the machine this was measured on
FRAME_MS = 1000.0 / FPS

ACTIONS = [
    ("move", "Move the cursor", "The hand steers the cursor."),
    ("drag", "Click and drag", "Press the mouse button while the pose is held; release when it ends."),
    ("right_click", "Right-click", "One right-click each time the pose starts."),
    ("scroll", "Scroll", "Move the hand up, down, left or right to scroll."),
    ("move_window", "Grab and move a window", "Takes hold of the window under the cursor once the hand moves."),
    ("toggle_maximize", "Maximise / restore", "Maximise the window under the cursor (again to restore)."),
    ("minimize", "Minimise", "Minimise the window under the cursor."),
    ("close_window", "Close window", "Ask the window under the cursor to close, like its X button."),
    ("none", "Do nothing", "The pose is recognised but does nothing."),
]
POSES = [
    ("palm", "Open palm", "all four fingers straight", "move"),
    ("point", "One finger", "only the index finger up", "none"),
    ("click", "Pinch", "thumb tip to index tip", "drag"),
    ("right", "Three fingers", "index, middle and ring up", "right_click"),
    ("scroll", "Two fingers", "index and middle up", "scroll"),
    ("fist", "Fist", "fingers clearly closed", "move_window"),
    ("thumb_up", "Thumbs-up", "thumb sticking straight up beyond the fist", "toggle_maximize"),
    ("thumb_down", "Thumbs-down", "thumb pointing straight down", "minimize"),
    ("ell", "L shape", "thumb out sideways, index up", "close_window"),
]


def opt(value, label, desc="", ms=None, tone="neutral", badge=None, basis=None):
    return {"value": value, "label": label, "desc": desc, "ms": ms, "tone": tone, "badge": badge, "basis": basis}


def num(id, label, desc, default, lo, hi, step, unit="", impact=None, advanced=False, precision=None):
    return {"id": id, "type": "number", "label": label, "desc": desc, "default": default, "min": lo, "max": hi, "step": step,
            "unit": unit, "impact": impact or {"kind": "none"}, "advanced": advanced, "precision": precision}


def boolean(id, label, desc, default, impact=None, advanced=False, requires=None):
    return {"id": id, "type": "bool", "label": label, "desc": desc, "default": default, "impact": impact or {"kind": "none"},
            "advanced": advanced, "requires": requires}


def enum(id, label, desc, default, options, impact=None, advanced=False, nullable=False):
    return {"id": id, "type": "enum", "label": label, "desc": desc, "default": default, "options": options,
            "impact": impact or {"kind": "options"}, "advanced": advanced, "nullable": nullable}


def note(text, tone="neutral", basis=None):
    return {"kind": "note", "text": text, "tone": tone, "basis": basis}


def frames(text, affects, basis="calculated"):
    return {"kind": "frames", "text": text, "affects": affects, "basis": basis}


def seconds(text, affects, basis="calculated"):
    return {"kind": "seconds", "text": text, "affects": affects, "basis": basis}


GROUPS = [
    {
        "id": "general", "label": "Startup", "icon": "bolt",
        "desc": "What happens when Hexra starts. Start with Windows is on the Overview page.",
        "settings": [
            boolean("start_control", "Start hand control automatically", "When Hexra starts, also switch on the camera and hand control, so it works at once without opening the window. Off: Hexra waits in the tray until you press Start.", False,
                    note("The camera light comes on and your hand controls the mouse as soon as Hexra starts.", "warn", "calculated")),
        ],
    },
    {
        "id": "cursor", "label": "Cursor & movement", "icon": "cursor",
        "desc": "How the cursor follows your hand: smoothness, speed and precision.",
        "settings": [
            enum("feel", "Feel", "How strongly Hexra smooths your hand's tremor. This is the main speed-versus-steadiness choice.", "responsive", [
                opt("responsive", "Responsive", "Least lag; a little more shake when your hand rests.", 17, "good", "about 17 ms", "simulation"),
                opt("balanced", "Balanced", "Good steadiness with moderate lag.", 28, "neutral", "about 28 ms", "simulation"),
                opt("smooth", "Smooth", "Steadiest for a trembling hand, but the cursor trails your hand.", 59, "warn", "about 59 ms", "simulation"),
            ]),
            enum("cursor_mode", "How the cursor follows your hand", "Relative works like a mouse: the cursor moves by how far your hand moves, with acceleration.", "relative", [
                opt("relative", "Relative (like a mouse)", "Slow hand = fine control, a quick flick crosses the screen. Lift your hand (one finger) to reposition.", 0, "good", "no extra delay", "calculated"),
                opt("absolute", "Absolute (copies your hand)", "The cursor goes where your hand is inside the active box. No acceleration; you can run out of arm.", 0, "neutral", "no extra delay", "calculated"),
            ]),
            enum("cursor_point", "Point that drives the cursor", "Which part of the hand the cursor tracks.", "knuckles", [
                opt("knuckles", "Average of four knuckles", "Steadier, and does not shift when you pinch.", 0, "good", "no extra delay", "calculated"),
                opt("index_knuckle", "Index knuckle only", "A single landmark: slightly shakier, shifts a little when pinching.", 0, "neutral", "no extra delay", "calculated"),
            ]),
            num("rel_gain_min", "Slow-move gain", "Cursor speed compared with hand speed for slow movements. Below 1 the cursor trails your hand and feels sluggish.", 1.1, 0.5, 3.0, 0.05, "x",
                note("Lower = finer control but feels laggier. At 0.34 the cursor followed only a third of a slow hand in simulation.", "warn", "simulation")),
            num("rel_gain_max", "Fast-move gain", "Cursor speed compared with hand speed for quick flicks. Higher lets a small flick cross the screen.", 3.0, 1.0, 8.0, 0.1, "x",
                note("No added delay. Too high makes fast moves hard to stop precisely.", "neutral", "calculated")),
            num("rel_v_low", "Acceleration starts at", "Hand speed (camera-widths per second) where the cursor starts to speed up.", 0.04, 0.01, 0.3, 0.01, "/s",
                note("No added delay.", "neutral", "calculated"), advanced=True),
            num("rel_v_high", "Acceleration ends at", "Hand speed where the cursor reaches its fastest gain.", 0.8, 0.2, 2.0, 0.05, "/s",
                note("No added delay.", "neutral", "calculated"), advanced=True),
            num("rel_softness", "Tremor filter", "Hand movements smaller than this per frame are treated as tremor and mostly ignored.", 0.0003, 0.0, 0.003, 0.0001, "",
                note("Higher = steadier at rest but the first tiny movements arrive late (a few ms).", "warn", "estimate"), advanced=True, precision=4),
            num("lead_ms", "Look-ahead", "Moves the cursor slightly ahead of your hand to cancel part of the webcam's own delay.", 0, 0, 40, 1, "ms",
                note("Each ms of look-ahead cancels about 1 ms of delay while you move, but overshoots when you stop: 40 ms is about 120 px.", "warn", "measured")),
            num("click_lookback_s", "Click snap-back", "A click lands where the cursor was this long BEFORE the pinch began, so the pinch does not push it off target.", 0.15, 0.0, 0.4, 0.01, "s",
                note("No added delay. 0 turns it off; higher can pull a click back to a place you already left.", "neutral", "calculated"), precision=2),
            num("click_snap_px", "Snap-back limit", "No snap-back when the cursor was really moving (it travelled more than this many pixels).", 100, 20, 300, 5, "px",
                note("No added delay.", "neutral", "calculated"), advanced=True),
            num("min_cutoff", "Custom filter: steadiness", "Overrides the Feel preset. Lower = steadier at rest, more lag. Leave empty to use the preset.", None, 0.1, 5.0, 0.1, "",
                note("Replaces the Feel preset's measured lag, so the lag shown in the estimate is not valid while this is set.", "warn", "calculated"), advanced=True),
            num("beta", "Custom filter: speed response", "Overrides the Feel preset. Higher = snappier when you move fast. Leave empty to use the preset.", None, 0.0, 100.0, 1.0, "",
                note("Replaces the Feel preset's measured lag.", "warn", "calculated"), advanced=True),
            num("deadzone_px", "Custom dead zone", "Overrides the Feel preset: the cursor ignores movement smaller than this. Leave empty to use the preset.", None, 0.0, 12.0, 0.5, "px",
                note("A bigger dead zone is steadier but the cursor creeps in steps.", "neutral", "calculated"), advanced=True),
        ],
    },
    {
        "id": "clicks", "label": "Clicks, drag & scroll", "icon": "click",
        "desc": "How quickly a pose counts, and how forgiving holds are when tracking flickers.",
        "settings": [
            num("hold_frames", "Hold before a click / right-click / scroll", "A pose must stay the same for this many camera frames before it clicks, right-clicks or starts scrolling. This stops a single misread frame from clicking.", 3, 1, 8, 1, "frames",
                frames("Every click, right-click and scroll waits this long after you make the pose.", ["Click delay"])),
            num("release_frames", "Hold before a drag ends", "How many frames of a different pose end a click-drag. Higher survives flicker; lower lets go sooner.", 6, 2, 15, 1, "frames",
                frames("A drag ends this long after you let go of the pinch.", ["Drag release"])),
            num("dropout_grace_s", "Keep holding through lost tracking", "If the camera briefly loses your hand (motion blur), a held drag or window is kept for up to this long.", 0.3, 0.0, 1.0, 0.05, "s",
                seconds("A hand you actually drop is released this long late.", ["Drag release"]), precision=2),
            num("scroll_gain", "Scroll speed", "How far the page scrolls per hand movement, in both directions.", 150, 20, 400, 10, "",
                note("No added delay.", "neutral", "calculated")),
            num("scroll_axis_lock", "Scroll direction lock", "Mostly up/down or mostly sideways movement scrolls one direction only. 1 = always diagonal.", 2.0, 1.0, 5.0, 0.1, "x",
                note("No added delay.", "neutral", "calculated"), advanced=True),
        ],
    },
    {
        "id": "windows", "label": "Windows", "icon": "window",
        "desc": "Grabbing, snapping, maximising, minimising and closing windows.",
        "settings": [
            num("grab_frames", "Hold before a fist counts", "A fist must stay closed for this many frames before it can take hold of a window.", 5, 1, 15, 1, "frames",
                frames("A grab cannot start sooner than this after you close your fist.", ["Window grab"])),
            num("grab_move_px", "Move before a window is grabbed", "A fist only takes hold of a window once your hand has moved this far. A still fist (for example on the way to a thumbs-up) touches nothing. 0 = grab at once.", 30, 0, 150, 5, "px",
                note("About a few millimetres of hand movement at 30 px. 0 grabs instantly but can un-maximise or move a window by accident.", "neutral", "simulation")),
            num("grab_release_frames", "Hold before a window is dropped", "How many frames of a clearly different pose drop a window you are moving.", 10, 2, 30, 1, "frames",
                frames("A window you let go of is dropped this long after you open your hand.", ["Window drop"])),
            num("command_hold_s", "Thumbs-up / thumbs-down hold", "How long to hold the pose before it maximises or minimises. A ring fills while you hold.", 0.5, 0.2, 1.5, 0.05, "s",
                seconds("This is the delay before maximise / minimise happens.", ["Maximise / minimise"]), precision=2),
            num("close_hold_s", "L shape (close) hold", "How long to hold the L shape before the window is asked to close. Longer on purpose: closing is the hardest to undo.", 1.5, 0.5, 3.0, 0.1, "s",
                seconds("This is the delay before a window is closed.", ["Close window"])),
            num("command_cooldown_s", "Pause after a command", "After a window command, a fist cannot grab a window for this long, so a hand relaxing out of a thumbs-up grabs nothing.", 0.8, 0.2, 2.0, 0.05, "s",
                seconds("A deliberate fist right after a command waits this long.", ["Window grab"]), precision=2),
            num("thumb_guard_s", "Pause after a thumbs pose", "After any thumbs pose is seen, even briefly, a fist cannot start a grab for this long.", 0.6, 0.0, 1.5, 0.05, "s",
                seconds("A deliberate fist right after a thumbs pose waits this long.", ["Window grab"]), advanced=True, precision=2),
            boolean("snap_edges", "Snap windows to screen edges", "Drag a window with a fist INTO a screen edge and open your hand: left or right edge = that half of the screen, top edge = maximise.", True,
                note("No added delay.", "neutral", "calculated")),
            num("snap_edge_px", "Snap zone width", "How close to the screen edge the cursor must be for a snap.", 30, 5, 120, 5, "px",
                note("No added delay. A wider zone snaps more easily.", "neutral", "calculated")),
        ],
    },
    {
        "id": "gestures", "label": "Gestures", "icon": "hand",
        "desc": "Choose what each hand pose does. Every pose can be reassigned or switched off.",
        "settings": [
            {"id": f"actions.{pid}", "type": "action", "label": label, "desc": f"{how[0].upper()}{how[1:]}.", "default": default, "options": [],
             "impact": {"kind": "action"}, "advanced": False, "pose": pid}
            for pid, label, how, default in POSES
        ],
    },
    {
        "id": "presence", "label": "Wake & presence", "icon": "eye",
        "desc": "When Hexra listens: raised hand, facing the screen, and (optionally) only your face.",
        "settings": [
            boolean("air.enabled", "Only react to a hand raised in the air", "A hand resting on a desk, your lap or your head is ignored. Hexra starts asleep and wakes with an open palm held in the air.", True,
                note("No added delay once awake.", "good", "calculated")),
            num("air.wake_seconds", "Wake: hold an open palm for", "How long to hold an open palm in the air to wake Hexra.", 1.0, 0.2, 3.0, 0.1, "s",
                seconds("This is the wait before the first gesture works after Hexra was asleep.", ["Wake-up"]), precision=1),
            num("air.sleep_seconds", "Sleep after the hand is down for", "How long your hand can stay out of the air zone before Hexra goes back to sleep.", 1.0, 0.3, 5.0, 0.1, "s",
                seconds("A hand lowered this long puts Hexra back to sleep.", ["Sleep"]), precision=1),
            num("air.max_center_y", "Air line (how low counts as 'raised')", "The blue line in the camera window: the green ball (the middle of your hand) must be above it. 0 = top of the picture, 1 = bottom.", 0.95, 0.5, 1.0, 0.01, "",
                note("No added delay. Lower = you must raise your hand higher.", "neutral", "calculated"), advanced=True, precision=2),
            num("air.edge_margin", "How much hand may be outside the picture", "Negative lets part of the hand be outside the camera picture and still count (-0.15 = up to 15%).", -0.15, -0.3, 0.1, 0.01, "",
                note("No added delay.", "neutral", "calculated"), advanced=True, precision=2),
            boolean("attention.enabled", "Only when I am facing the screen", "Turn your head away to talk to a friend or look at your phone and Hexra pauses by itself; look back and it carries on. Uses a tiny face detector; it does not identify you.", False,
                note("Adds no delay to the cursor (it runs on a background thread). Gestures pause about the grace time after you look away.", "good", "calculated")),
            num("attention.max_turn_deg", "Looking away starts at", "A head turned further than this counts as looking away. Raise it if your camera sits to one side of the screen.", 35, 15, 70, 1, "deg",
                note("The camera window shows your live head turn, which is the way to tune this.", "neutral", "estimate")),
            num("attention.grace_s", "Looking away: pause after", "You must look away this long before gestures pause, so a glance at the keyboard changes nothing.", 1.0, 0.2, 3.0, 0.1, "s",
                seconds("Gestures keep working this long after you turn away.", ["Pause when looking away"]), precision=1),
            num("attention.check_every_s", "Face check interval", "How often a camera picture is checked for your face.", 0.2, 0.1, 1.0, 0.05, "s",
                seconds("Gestures can come back up to this long after you look at the screen again. Lower uses a little more CPU.", ["Resume when looking back"]), advanced=True, precision=2),
            boolean("attention.require_face", "No face in the picture counts as looking away", "On: if your face is not seen at all, gestures pause. Off: only a clearly turned face pauses them.", True,
                note("No added delay.", "neutral", "calculated"), advanced=True),
            boolean("face_lock.enabled", "Only recognise my face (face lock)", "Gestures work only while the enrolled administrator's face is recognised. Needs a one-time enrolment (Hexra.exe enroll) and the face-recognition model, which is not included in the standard installer.", False,
                note("Runs on a background thread: no cursor delay. Gestures resume up to the check interval after your face is recognised.", "neutral", "calculated"), requires="face_models"),
            num("face_lock.threshold", "Face match strictness", "Similarity needed to count as the administrator. Higher is stricter (0.45 is strict).", 0.365, 0.2, 0.7, 0.005, "",
                note("A higher value can reject you in poor light.", "warn", "calculated"), advanced=True, precision=3),
            num("face_lock.grace_s", "Keep working after the face was last seen", "You still count as present this long after the camera last recognised you.", 3.0, 0.5, 10.0, 0.5, "s",
                seconds("Another person at the keyboard can use Hexra for up to this long after you leave.", ["Lock delay"]), advanced=True, precision=1),
            num("face_lock.check_every_s", "Face-lock check interval", "How often a picture is checked for the administrator's face.", 0.4, 0.2, 2.0, 0.1, "s",
                seconds("Gestures resume up to this long after your face is recognised.", ["Unlock delay"]), advanced=True, precision=1),
            boolean("face_lock.require_face", "Locked unless my face is seen", "On: no face at all keeps it locked. Off: only an unknown face locks it.", True,
                note("No added delay.", "neutral", "calculated"), advanced=True),
        ],
    },
    {
        "id": "camera", "label": "Camera & screens", "icon": "camera",
        "desc": "The picture Hexra works from, and which screens it controls.",
        "settings": [
            {"id": "camera.use", "type": "cameras", "label": "Cameras", "desc": "Choose one camera, or two to use them together. With two, each camera tracks your hand; the one with the better view decides the pose and both steady the cursor. If one loses your hand, the other carries on. Face-direction pausing is switched off with two cameras.",
             "default": [0], "impact": {"kind": "none"}, "advanced": False},
            enum("camera.resolution", "Camera picture size", "A bigger picture gives the hand tracker more detail, at the cost of a little time per frame.", "640x480", [
                opt("640x480", "640 x 480", "The default: fastest and plenty for most distances.", 0, "good", "fastest", "measured"),
                opt("1280x720", "1280 x 720", "More detail for small or far hands.", 1.5, "neutral", "+1.5 ms per frame", "measured"),
                opt("1920x1080", "1920 x 1080", "Only for a hand far from the camera. Many webcams drop below 30 fps at this size, which makes everything slower.", 4, "warn", "may lower fps", "estimate"),
            ]),
            enum("screen.span", "Screens to control", "By default your hand controls ALL connected screens as one desktop.", "all", [
                opt("all", "All screens together", "Cursor, clicks, scrolling and window moves reach every screen.", 0, "good", "no extra delay", "calculated"),
                opt("primary", "Main screen only", "Keeps the cursor on the main screen.", 0, "neutral", "no extra delay", "calculated"),
            ]),
            enum("screen.monitor", "Or control just one screen", "Pick a single screen (1 = main, then the others left to right). 'Automatic' uses the setting above.", None, [
                opt(None, "Automatic", "Use the screens setting above.", 0, "good", "no extra delay", "calculated"),
                opt(1, "Screen 1 (main)", "", 0, "neutral", "no extra delay", "calculated"),
                opt(2, "Screen 2", "", 0, "neutral", "no extra delay", "calculated"),
                opt(3, "Screen 3", "", 0, "neutral", "no extra delay", "calculated"),
            ], nullable=True),
            {"id": "region", "type": "region", "label": "Active box (absolute mode)", "desc": "The part of the camera picture that maps to your whole screen when the cursor copies your hand. Smaller = less reaching. Not used in relative mode.",
             "default": [0.2, 0.15, 0.8, 0.7], "impact": note("No added delay.", "neutral", "calculated"), "advanced": False},
        ],
    },
]

# Presets: a name, a one-line promise, the values it sets, and the honest cost.
PRESETS = [
    {"id": "responsive", "label": "Fastest", "icon": "bolt", "desc": "Least delay. A little more shake when your hand rests.",
     "cost": "about 17 ms of filter lag", "values": {"feel": "responsive", "cursor_mode": "relative", "hold_frames": 2, "lead_ms": 0, "camera.resolution": "640x480"}},
    {"id": "balanced", "label": "Balanced", "icon": "scale", "desc": "Steady and quick. A good everyday choice.",
     "cost": "about 28 ms of filter lag", "values": {"feel": "balanced", "cursor_mode": "relative", "hold_frames": 3, "lead_ms": 0, "camera.resolution": "640x480"}},
    {"id": "steady", "label": "Steadiest", "icon": "anchor", "desc": "For a trembling hand: heavy smoothing and slower, more deliberate clicks.",
     "cost": "about 59 ms of filter lag, clicks 133 ms", "values": {"feel": "smooth", "cursor_mode": "relative", "hold_frames": 4, "release_frames": 8, "rel_softness": 0.0008, "camera.resolution": "640x480"}},
    {"id": "presenter", "label": "Presenter", "icon": "screen", "desc": "Far from the camera: bigger picture, only reacts when you face the screen.",
     "cost": "about 1.5 ms more per frame, balanced filter", "values": {"feel": "balanced", "camera.resolution": "1280x720", "attention.enabled": True, "air.enabled": True}},
]


def flatten():
    return [s for g in GROUPS for s in g["settings"]]


def by_id():
    return {s["id"]: s for s in flatten()}


def defaults() -> dict:
    return {s["id"]: s["default"] for s in flatten()}


def schema_json() -> dict:
    return {"fps": FPS, "frame_ms": FRAME_MS, "groups": GROUPS, "presets": PRESETS, "actions": [{"value": v, "label": l, "desc": d} for v, l, d in ACTIONS],
            "poses": [{"id": i, "label": l, "how": h, "default": d} for i, l, h, d in POSES]}


# ---------------------------------------------------------------------------------------------------------------- validation
class SettingError(ValueError):
    pass


def validate_value(setting: dict, value):
    """The cleaned value, or a SettingError. Numbers are clamped into range and rounded to the step; unknown choices are refused."""
    t = setting["type"]
    if t == "bool":
        if not isinstance(value, bool):
            raise SettingError(f"{setting['label']}: must be on or off")
        return value
    if t == "number":
        if value is None:
            if setting["default"] is None:
                return None                                     # an optional override left empty
            raise SettingError(f"{setting['label']}: a number is required")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SettingError(f"{setting['label']}: must be a number")
        lo, hi, step = setting["min"], setting["max"], setting["step"]
        if not (lo - 1e-9 <= value <= hi + 1e-9):
            raise SettingError(f"{setting['label']}: must be between {lo} and {hi}")
        digits = max(0, len(str(step).split(".")[1]) if "." in str(step) else 0)
        v = round(round(value / step) * step, max(digits, 4))
        if all(isinstance(x, int) for x in (setting["min"], setting["max"], step)) and isinstance(setting["default"], int):
            v = int(round(v))
        return min(max(v, lo), hi)
    if t == "enum":
        allowed = [o["value"] for o in setting["options"]]
        if value not in allowed:
            raise SettingError(f"{setting['label']}: {value!r} is not one of {allowed}")
        return value
    if t == "action":
        if value not in {a[0] for a in ACTIONS}:
            raise SettingError(f"{setting['label']}: unknown action {value!r}")
        return value
    if t == "cameras":
        ok = isinstance(value, list) and 1 <= len(value) <= 2 and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 7 for x in value)
        if not ok or len(set(value)) != len(value):
            raise SettingError("Cameras: choose one or two different cameras")
        return sorted(value)
    if t == "region":
        if not (isinstance(value, list) and len(value) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value)):
            raise SettingError("Active box: four numbers (left, top, right, bottom)")
        x0, y0, x1, y1 = (round(float(x), 3) for x in value)
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise SettingError("Active box: left < right and top < bottom, all between 0 and 1")
        if (x1 - x0) < 0.1 or (y1 - y0) < 0.1:
            raise SettingError("Active box: at least 10% of the picture in each direction")
        return [x0, y0, x1, y1]
    raise SettingError(f"{setting['id']}: unknown setting type")


def validate_all(values: dict) -> dict:
    """Validate a dict of {setting id: value}. Unknown ids are refused. Also checks relationships between settings."""
    table = by_id()
    clean = {}
    for key, val in values.items():
        if key not in table:
            raise SettingError(f"unknown setting: {key}")
        clean[key] = validate_value(table[key], val)
    if len(clean.get("camera.use", [0])) > 1 and clean.get("attention.enabled"):
        clean["attention.enabled"] = False                      # face-direction pausing needs one camera that faces you
    lo, hi = clean.get("rel_v_low"), clean.get("rel_v_high")
    if lo is not None and hi is not None and lo >= hi:
        raise SettingError("Acceleration must start at a lower hand speed than it ends")
    g0, g1 = clean.get("rel_gain_min"), clean.get("rel_gain_max")
    if g0 is not None and g1 is not None and g0 > g1:
        raise SettingError("Slow-move gain cannot be higher than fast-move gain")
    return clean
