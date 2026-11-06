"""Part 1 of the guide: overview, install, first run, gestures, daily use, settings."""
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Spacer

from pdf_lib import (RED, AMBER, BLUE, BODY, B, H1, H2, H3, P, SMALL, accel_curve, callout, code, hand_glyph, landmark_diagram, pipeline_diagram,
                     pose_strip, table)


def part1():
    s = []
    s += [P("1. What this program is", H1)]
    s += [P("Hexra lets you run your computer with your hand in front of a webcam, with no mouse touched. "
            "It moves the cursor, clicks, drags, right-clicks, scrolls in four directions and moves any window you point at. "
            "It is built to feel like a mouse (smooth, accelerated, precise), it works across several screens, it ignores a "
            "hand that is not deliberately raised in the air, and it only obeys the administrator: the person whose face was "
            "enrolled on first start."),
          P("This document is both a user guide and a record of the project: how it started, what was wrong at each step, what "
            "was changed, and why. Part A (sections 1 to 7) is for using the program. Part B (sections 8 to 11) explains how it "
            "works inside, module by module. Part C (sections 12 to 17) is the history, the test results, the limits and the "
            "installer.")]
    s += table([["You want to...", "Go to"],
                ["install and start it", "section 2 and 3"],
                ["know which hand shape does what", "section 4"],
                ["change speed, smoothness, screens, sensitivity", "section 6"],
                ["fix something that misbehaves", "section 7"],
                ["understand how it works", "sections 8 to 11"],
                ["see every change made since the first version", "section 12"],
                ["rebuild the installer", "section 16"]], [80, 85])
    s += callout("This release has no face lock",
                 "For now the installed program ships <b>without</b> the face lock: no face models are included, nothing asks you to enrol, and anyone in front of the camera "
                 "can use the gestures. Every description of the face lock in this guide (sections 3, 5, 7, 10.6, 11) is about the feature in the development project, "
                 "where it is still built and tested; it can be switched back on later.", RED)
    s += callout("Honest status of what you are reading",
                 "Most behaviour here was tuned using simulated hands (a mathematical model of a hand turned, curled and shaking) "
                 "and automated tests, because the assistant could not watch your real hand. Everything marked <b>confirmed by you</b> "
                 "was reported working on your own PC. Everything else is described as built and tested in simulation only. "
                 "Section 14 lists the known weak spots.", AMBER)

    s += [PageBreak(), P("2. Installing", H1)]
    s += [P("You received one file, <b>Hexra-Setup.exe</b>. Everything the program needs is inside it: the program, its "
            "libraries, the hand-tracking model and this guide. Nothing is downloaded during "
            "setup or later.")]
    s += [P("Steps", H3)]
    s += B(["Double-click <b>Hexra-Setup.exe</b>.",
            "Windows may show <i>Windows protected your PC</i>. The file is not code-signed (signing costs money and needs a registered "
            "publisher), so Windows warns about every unsigned download. Click <b>More info</b>, then <b>Run anyway</b>. "
            "Some antivirus programs also flag programs packed with PyInstaller; if yours does, allow the file.",
            "Choose the folder (default <font face='Courier'>%LOCALAPPDATA%\\Programs\\Hexra</font>, which needs no "
            "administrator rights), tick the shortcuts you want, press <b>Install</b>.",
            "Setup copies about 135 MB, creates shortcuts, and registers the program in <i>Settings > Apps</i> so you can remove it later.",
            "Leave <i>Start Hexra when setup finishes</i> ticked to go straight to the first run."])
    s += [P("Silent install (for IT or scripts)", H3),
          code("Hexra-Setup.exe /S\nHexra-Setup.exe /S /DIR=D:\\Apps\\Hexra /NOSHORTCUTS"),
          P("Re-running setup over an existing install updates the program but keeps your <font face='Courier'>config.yaml</font>, your "
            "enrolled face and your logs.")]
    s += [P("What gets installed", H3)]
    s += table([["Item", "Where", "Purpose"],
                ["Hexra.exe + _internal\\", "install folder", "the program and its Python/MediaPipe/OpenCV libraries"],
                ["models\\hand_landmarker.task", "install folder", "Google MediaPipe hand model (7.8 MB)"],
                ["(face models)", "not included", "this release has no face lock, so the two face models (about 39 MB) are left out"],
                ["config.yaml", "install folder", "all settings, with comments; edit with Notepad"],
                ["data\\", "install folder", "created on first run: admin_face.npz (face fingerprints), last_run.log"],
                ["User Guide.pdf", "install folder", "this document"],
                ["Shortcuts", "Desktop, Start Menu > Hexra", "start, try-it mode, re-enrol face, user guide, uninstall"],
                ["Uninstall entry", "registry, current user only", "Settings > Apps > Hexra"]], [50, 45, 70])
    s += [P("Removing it", H3),
          P("Use <i>Settings > Apps > Hexra > Uninstall</i>, or the Start Menu entry, or run "
            "<font face='Courier'>Hexra.exe uninstall</font>. It deletes the whole folder, <b>including the saved face "
            "fingerprints</b>, the shortcuts and the registry entry.")]

    s += [PageBreak(), P("3. First start", H1)]
    s += [P("Start <b>Hexra</b> from the desktop or Start Menu. A black console window opens (it shows what the program is "
            "doing and is where messages appear) and a camera window appears.")]
    s += [P("Step 1: enrol your face (once)", H3)]
    s += B(["On the very first start nobody is enrolled, so the program opens a window titled <i>enrol admin face</i>.",
            "Look at the camera so that <b>only you</b> are in the picture. Samples are only taken when exactly one face is visible.",
            "It takes 18 samples. Turn your head slightly left and right, tilt up and down, and smile, so the program learns your face "
            "in different poses.",
            "It stores 128 numbers per sample (a fingerprint), never photos, in <font face='Courier'>data\\admin_face.npz</font>.",
            "If the samples are too few or too alike it tells you and asks you to retry. Esc cancels and saves nothing.",
            "Later: <font face='Courier'>Hexra.exe enroll --add</font> adds samples (glasses, other lighting), "
            "<font face='Courier'>enroll --clear</font> forgets you. The Start Menu has <i>Enrol or re-enrol my face</i>."])
    s += [P("Step 2: wake it", H3),
          P("The program starts <b>asleep</b> so that a resting hand cannot do anything. Raise your hand into the air with an open palm "
            "and hold it for <b>one second</b>. The overlay shows <i>WAKING... 60%</i> and then the gestures are live.")]
    s += [P("Step 3: engage", H3),
          P("Real control starts <b>paused</b>. Press <b>F8</b> (or click the camera window and press <b>e</b>) until the top line says "
            "<font face='Courier'>ENGAGED</font>. Press F8 again to pause. <b>F9</b> (or <b>q</b> in the camera window) quits.")]
    s += callout("Want to try it without risk?",
                 "Start <i>Hexra (try it, mouse untouched)</i> from the Start Menu (it runs with <font face='Courier'>--dry-run</font>). "
                 "It tracks your hand and shows the recognised pose, but never moves your mouse or windows.")
    s += [P("What the camera window shows", H3)]
    s += table([["On screen", "Meaning"],
                ["top line: ENGAGED / PAUSED, pose, fps, ms", "control state; the pose the program currently believes; frames per second (30 is your camera's limit); "
                 "software delay in milliseconds from the moment a picture was taken to the moment the mouse was told to move"],
                ["yellow rectangle", "the 'active box' (config key <i>region</i>). In the default relative mouse-like mode it does not limit anything"],
                ["green circle on the hand (red while clicking)", "the point that drives the cursor: the average of your four knuckles"],
                ["blue horizontal line", "the air line. The green circle must be ABOVE it for the hand to count"],
                ["orange text: ASLEEP / WAKING / hand not in the air", "air-gate state"],
                ["red LOCKED", "your face is not recognised; hands are ignored"],
                ["small text under the top line", "face-lock status (similarity score)"],
                ["yellow-orange note", "events such as 'window grabbed', shown for 3 seconds"]], [58, 107])

    s += [PageBreak(), P("4. The gestures", H1)]
    s += [P("Six hand shapes. Use either hand; one hand at a time is tracked. Always keep the hand raised in the air and roughly facing "
            "the camera.")]
    s += pose_strip([dict(up=(1, 1, 1, 1), label="Open palm"), dict(up=(1, 0, 0, 0), label="One finger"),
                     dict(up=(0, 0, 0, 0), pinch=True, label="Pinch"), dict(up=(1, 1, 1, 0), label="Three fingers"),
                     dict(up=(1, 1, 0, 0), label="Two fingers"), dict(up=(0, 0, 0, 0), fist=True, label="Fist")])
    s += table([["Hand shape", "How to make it", "What it does"],
                ["<b>Open palm</b>", "all four fingers straight, spread a little", "<b>Moves the cursor.</b> Also the wake gesture (hold 1 s). "
                 "Any hand shape the program is unsure about counts as an open palm, which can only move the cursor, never click or grab."],
                ["<b>One finger</b>", "only the index finger up, the rest curled", "<b>Pause the cursor</b> without leaving the picture. In "
                 "mouse-like mode it is 'lifting the mouse': move your hand back to a comfortable spot, open your palm again, and the cursor continues from where it was."],
                ["<b>Pinch</b>", "touch thumb tip to index tip", "<b>Left click</b>. Keep pinching and move to <b>drag</b>. Release the pinch to drop."],
                ["<b>Three fingers</b>", "index, middle and ring up; pinky and thumb folded", "<b>Right click</b>, once per pose."],
                ["<b>Two fingers</b>", "index and middle up, ring and pinky folded", "<b>Scroll</b>: move your hand up or down for vertical scroll, left or right "
                 "for horizontal. It does not scroll while you hold still. Mostly vertical or mostly sideways movement scrolls one axis only."],
                ["<b>Fist</b>", "all fingers clearly closed", "<b>Grab the window under the cursor</b> (not the window in front) and move it as your hand moves. "
                 "Open the hand to drop it. A maximised window is restored first so that it can move. The desktop and taskbar are never grabbed."]],
               [28, 52, 85])
    s += [P("Window commands", H3),
          P("Three more poses act on the <b>window under the cursor</b>. Each is a <i>held</i> pose: a ring fills in the camera window, nothing happens until it is full, "
            "and dropping the pose cancels it.")]
    s += table([["Hand shape", "Hold", "What it does"],
                ["<b>Thumbs-up</b>: a fist with the thumb sticking straight up, clearly beyond the fist (a thumb resting along a fist does not count)", "0.5 s", "<b>Maximise</b>; again to restore"],
                ["<b>Thumbs-down</b>: a fist with the thumb straight down", "0.5 s", "<b>Minimise</b>"],
                ["<b>L shape</b>: thumb out sideways, index finger up, the rest closed", "1.5 s (red ring)", "<b>Close</b>: the same as clicking the window's X, so the program can still ask to save"],
                ["<b>Fist dragged INTO a screen edge, then opened</b>", "release", "<b>Snap</b>: left or right edge = that half of the screen, top edge = maximise. A live hint appears in the zone"]],
               [66, 28, 71])
    s += callout("Why these cannot be confused with the movement poses",
                 "No pose is shared. They never act on the desktop, the taskbar or Hexra's own windows; they cannot start while you hold a fist or a pinch (a thumb sticking out of a dragging fist is ignored); "
                 "and a fist cannot grab a window for 0.8 s after a command, so a hand relaxing out of a thumbs-up grabs nothing. An L is close to pointing with the thumb out, so close needs the long hold and shows its ring.", AMBER)
    s += [P("Rules of thumb", H3)]
    s += B(["<b>Scroll is about movement</b>, not about holding your hand straight. Make the two-finger shape, then move the hand.",
            "<b>Aim first, then act.</b> Open palm to put the cursor on the target, then pinch (or make the fist).",
            "<b>Pinching does not push the click off target.</b> A click lands where the cursor was 0.15 s before the pinch began, "
            "unless you were really moving (more than 100 pixels), in which case it lands where you are.",
            "<b>The fist is deliberate.</b> It needs index, middle and ring clearly folded for about 0.17 s. Half-curled fingers do not grab a window. "
            "And a fist only takes hold of a window <b>once your hand moves</b> (about 30 pixels): a fist that stays still, such as the one on the way to a thumbs-up, touches nothing, not even to un-maximise the window.",
            "<b>Dropping a window is also deliberate.</b> Holding a fist survives wobbles; the window is released only after about 0.33 s of clearly open hand. "
            "A click-drag needs about 0.2 s of a different pose to end.",
            "<b>Losing the hand</b> for less than 0.3 s (motion blur) does not release anything held. Longer than that releases the click or window.",
            "<b>Keep the hand a comfortable arm's length away</b>, wrist visible, palm toward the camera. A hand turned sideways loses accuracy (section 14)."])
    s += callout("Why the poses are shaped this way",
                 "Earlier versions used a thumb-middle pinch for right click, which looked like pointing (a curled middle finger sits near the thumb). "
                 "Two fingers and three fingers swapped roles twice at your request. The final set was chosen so that no two poses share a finger "
                 "pattern, and so that the neutral pose (one finger) can never click.")

    s += [P("5. Daily use", H1)]
    s += [P("The air gate", H2),
          P("A hand resting on a desk, in your lap or against your head must not move the cursor. The gate therefore requires that the "
            "green circle (your knuckle average) is above the blue line, and that the hand is inside the picture, with 15% leeway "
            "past each edge so that a hand partly out of frame still counts. When the hand leaves the zone for one second, the program "
            "goes back to sleep and needs the one-second open-palm wake gesture. While you are holding a click-drag or a window, a more "
            "relaxed check applies so that reaching to a screen edge does not drop what you hold.")]
    s += [P("The face lock", H2),
          P("Gestures work only while the administrator's face has been recognised in the camera picture within the last 3 seconds. "
            "Looking down at the keyboard briefly is fine. Someone else's face does not unlock it. If your face is not found at all, "
            "the lock stays closed (this is <i>require_face: true</i>). The check runs on a background thread twice or so a second so "
            "it never delays the cursor. It is a convenience lock, not strong security: a photo or video of you can fool it, and it "
            "identifies a face, not whose hand is moving.")]
    s += [P("Several screens", H2),
          P("By default every connected screen is one big desktop. The cursor, clicks, scrolling and window grabbing reach all of them, whichever side "
            "or above/below they sit on and whatever their sizes. Your PC logged a combined desktop of 6400 x 2160 pixels when a second screen "
            "was attached. To control one screen only, set <font face='Courier'>screen: span: primary</font> or "
            "<font face='Courier'>screen: monitor: 2</font> in config.yaml.")]
    s += [P("Mouse-like movement", H2),
          P("The cursor moves by how far your hand moves, with acceleration. Slow movement gives fine control, a quick flick crosses the screen. "
            "The curve below is the default (gain 1.1 for slow movement rising smoothly to 3.0 for fast movement; the rise starts at 0.04 and "
            "ends at 0.8 camera-widths per second):"), accel_curve(),
          P("Setting <font face='Courier'>cursor_mode: absolute</font> instead makes the cursor copy your hand's position inside the yellow box.", SMALL)]

    s += [PageBreak(), P("6. All settings (config.yaml)", H1)]
    s += [P("config.yaml sits in the install folder. Open it with Notepad, change a value, save, and restart the program. A key that is "
            "missing uses its default. If you break the file, delete it and the defaults apply.")]
    s += table([["Key", "Default", "What it changes"],
                ["screen.span", "all", "<i>all</i>: every screen together. <i>primary</i>: main screen only"],
                ["screen.monitor", "-", "control just one screen (1 = main, then the others left to right)"],
                ["region", "[0.2, 0.15, 0.8, 0.7]", "active box in the camera picture (x0, y0, x1, y1 as fractions). Used by absolute mode"],
                ["feel", "responsive", "smooth (steadiest, ~59 ms filter lag) / balanced (~28 ms) / responsive (~17 ms, a little more shake)"],
                ["cursor_mode", "relative", "relative = like a mouse; absolute = cursor copies the hand position"],
                ["rel_gain_min / rel_gain_max", "1.1 / 3.0", "cursor speed relative to hand speed for slow / fast movement"],
                ["rel_v_low / rel_v_high", "0.04 / 0.8", "hand speeds where acceleration starts and finishes"],
                ["rel_softness", "0.0003", "per-frame hand movement below this is treated as tremor"],
                ["cursor_point", "knuckles", "average of four knuckles (steadier). index_knuckle = single landmark (older behaviour)"],
                ["click_lookback_s / click_snap_px", "0.15 / 100", "click lands where the cursor was this long before the pinch, unless you moved farther than the pixel limit. 0 turns it off"],
                ["camera.width / height", "640 / 480", "try 1280 / 720 for more detail (about 1.5 ms slower per frame)"],
                ["min_cutoff, beta, deadzone_px", "from feel", "advanced override of the smoothing filter"],
                ["hold_frames", "3", "frames a click, right click or scroll must persist (cursor move needs 2)"],
                ["grab_frames", "5", "frames a fist must persist to grab a window (~0.17 s)"],
                ["release_frames", "6", "frames a different pose must persist to end a click-drag"],
                ["grab_release_frames", "10", "frames (~0.33 s) to drop a grabbed window"],
                ["command_hold_s / close_hold_s", "0.5 / 1.5", "seconds to hold thumbs-up or thumbs-down / the L shape before the command fires"],
                ["grab_move_px", "30", "a fist takes hold of a window only after the hand has moved this far (screen pixels); 0 = at once"],
                ["thumb_guard_s", "0.6", "after a thumbs pose is seen, a fist cannot grab a window for this long (a hand relaxing out of it)"],
                ["command_cooldown_s", "0.8", "after a command, a fist cannot grab a window for this long"],
                ["snap_edges / snap_edge_px", "true / 30", "snap a fist-dragged window released at a screen edge; how close to the edge counts, in pixels"],
                ["dropout_grace_s", "0.3", "keep holding through brief tracking losses up to this long"],
                ["scroll_gain", "150", "scroll speed (both axes)"],
                ["scroll_axis_lock", "2.0", "mostly-vertical or mostly-horizontal movement scrolls one axis only (1.0 = always diagonal)"],
                ["actions", "see below", "which pose does which action"],
                ["air.enabled / wake_seconds / sleep_seconds", "true / 1.0 / 1.0", "air gate on/off; seconds of open palm to wake; seconds out of the air before sleeping"],
                ["air.max_center_y", "0.95", "the blue line position (0 = top of picture, 1 = bottom)"],
                ["air.edge_margin", "-0.15", "negative lets the hand be partly outside the picture"],
                ["lead_ms", "0", "look-ahead; off because it overshoots when you stop"],
                ["face_lock.enabled", "true", "false turns the lock off for everyone"],
                ["face_lock.threshold", "0.363", "similarity needed to count as the admin (0.45 is stricter)"],
                ["face_lock.grace_s", "3.0", "you still count as present this long after the last match"],
                ["face_lock.check_every_s", "0.4", "how often a picture is checked"],
                ["face_lock.require_face", "true", "true: locked unless your face is seen. false: only an unknown face locks it"]], [47, 32, 86])
    s += [P("Changing what a pose does", H3),
          code("actions:\n  palm: move          # move | drag | right_click | scroll | move_window | toggle_maximize | minimize | close_window | none\n  fist: move_window\n"
               "  point: none\n  click: drag\n  right: right_click\n  scroll: scroll\n  thumb_up: toggle_maximize\n  thumb_down: minimize\n  ell: close_window"),
          P("Command-line options (add them to a shortcut's target or run from a terminal):", BODY)]
    s += table([["Command", "Effect"],
                ["Hexra.exe", "start normally"],
                ["Hexra.exe --dry-run", "show poses, never touch the mouse or windows"],
                ["Hexra.exe --no-face-lock", "run once without the face lock"],
                ["Hexra.exe --config other.yaml", "use another settings file"],
                ["Hexra.exe enroll [--add | --clear | --samples N]", "enrol, add samples, or forget the admin face"],
                ["Hexra.exe precision [--width W --height H]", "measure how steady the cursor point is on your camera (hold the open hand still for 8 s)"],
                ["Hexra.exe selftest", "check every part loads (no camera needed)"],
                ["Hexra.exe uninstall", "remove the program"]], [85, 80])
    return s
