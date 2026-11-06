"""Part 2: troubleshooting, architecture, module reference, algorithms, privacy."""
from reportlab.platypus import PageBreak

from pdf_lib import AMBER, BODY, B, H1, H2, H3, P, SMALL, callout, code, landmark_diagram, pipeline_diagram, table


def part2():
    s = []
    s += [PageBreak(), P("7. When something misbehaves", H1)]
    s += [P("The first stop is the top line of the camera window and the file <font face='Courier'>data\\last_run.log</font> in the install folder "
            "(rewritten at every start). It lists the screen size found, the recogniser, face-lock state, and every pose change or hold/release event.")]
    s += table([["What you see", "Likely cause", "What to do"],
                ["Hands are tracked but nothing moves", "(a) --dry-run mode, or (b) the program is PAUSED, or (c) the air gate is asleep, or (d) LOCKED",
                 "read the top line: PAUSED -> press F8 or 'e'; ASLEEP -> open palm for 1 s; LOCKED -> your face is not recognised (see below)"],
                ["Window says LOCKED although it is you", "bad light, face too small, looking away for more than 3 s, glasses/hat different from enrolment",
                 "improve light, face the camera, run Enrol with --add, or lower face_lock.threshold slightly (0.3)"],
                ["'Could not open the webcam'", "another program (Teams, Zoom, a second copy of this app) holds the camera",
                 "close the other program; only one program can use the camera at a time"],
                ["Cursor ignores a hand that is fully visible", "the green circle is below the blue line, or hand mostly outside the picture",
                 "raise the hand, or raise air.max_center_y toward 0.97, or make edge_margin more negative"],
                ["Open palm is read as right click when I rotate my hand", "fixed in this version (finger straightness instead of distance from the wrist)",
                 "if it still happens, tell the maintainer the angle; section 14 lists the remaining weak angles"],
                ["Two scrolling fingers curl and a window is grabbed", "fixed: a fist needs three fingers clearly folded and a 0.17 s hold; scroll tolerates relaxing",
                 "keep the two fingers reasonably straight; increase grab_frames to 7 for extra caution"],
                ["A held window or drag lets go in the middle", "fist or pinch briefly read as another pose",
                 "increase grab_release_frames (window) or release_frames (drag); check the log for 'pose changed to ...'"],
                ["Cursor feels laggy", "heavy smoothing, camera at 30 fps (hard limit), preview cost",
                 "feel: responsive; keep camera.width 640; the ms figure on screen is software delay only; your webcam adds ~50-100 ms of its own that no software can remove"],
                ["Cursor shakes when the hand is still", "tremor passing the filter",
                 "feel: balanced or smooth; raise rel_softness a little (0.0006)"],
                ["Click lands slightly off target", "the pinch moved the hand", "click_lookback_s is already 0.15; raise to 0.2 if you still drift"],
                ["Cannot reach the far screen", "span set to primary, or a monitor on another graphics adapter",
                 "screen: span: all; check 'Controlling N screens' at the top of last_run.log"],
                ["Black window closes immediately", "an error", "run it from a terminal (Start > cmd > the install path) or read data\\last_run.log"],
                ["A window is minimised, maximised or closed when I did not mean it", "a thumb held out looked like thumbs-up/down or an L (closest to pointing with the thumb out)",
                 "keep the thumb tucked when pointing; raise command_hold_s / close_hold_s; or remap or disable a pose in config.yaml (set its action to none)"],
                ["Dragging a window to the edge does not snap", "the cursor was not within snap_edge_px of the screen edge when you opened the fist", "drag until the hint 'release to snap' appears; raise snap_edge_px"],
                ["Windows warns about the installer", "the file is not code-signed", "More info > Run anyway; see section 2"]], [47, 54, 64])

    s += [P("8. How the program is built", H1)]
    s += [P("The program is a loop that runs once for every camera picture, about 30 times a second. Three things run beside it on their "
            "own threads so that they can never delay the cursor: the camera reader, the preview window and the face check.")]
    s += [pipeline_diagram()]
    s += [P("Order of events for one frame", H3)]
    s += B(["<b>Camera thread</b> keeps only the newest frame and the exact moment it was captured. A stale buffered frame is never processed; "
            "stale frames used to add 100 ms or more of lag in the common way of reading a webcam.",
            "The picture is <b>mirrored</b> (so that moving your right hand to the right moves the cursor right) and given to <b>MediaPipe</b>, "
            "which returns 21 numbered points per hand (picture below). Finding the hand takes about 8-9 ms.",
            "The <b>pose recogniser</b> turns the 21 points into one of six pose names.",
            "If the face lock is on, the newest frame is handed to its background thread, and the loop asks one yes/no question: is the admin here? "
            "If not, the hand is discarded for this frame.",
            "The <b>air gate</b> decides whether the hand counts (raised, inside the picture, program awake).",
            "The <b>controller</b> debounces the pose, runs the state machine, filters the hand position and calls the mouse and the window mover.",
            "The loop draws overlays and gives the picture to the <b>preview thread</b>, then immediately waits for the next frame."])
    s += [landmark_diagram()]

    s += [PageBreak(), P("9. Module reference", H1)]
    s += [P("Every file in <font face='Courier'>src/hexra/</font>, what it contains and why it exists. The project has about 1,900 lines "
            "of program code and 1,050 lines of tests.")]
    s += table([["File", "Role"],
                ["<b>__main__.py</b>", "lets <font face='Courier'>python -m hexra</font> start the app"],
                ["<b>app.py</b>", "the main loop (section 8). Reads config.yaml (screen, feel presets, cursor mode, thresholds, air gate, camera, face lock), starts logging to data/last_run.log, "
                 "starts the hotkey listener (F8 engage, F9 quit), draws the overlays, shows notes for 3 s. Options: --dry-run, --rule, --no-face-lock, --config."],
                ["<b>camera.py</b>", "<b>ThreadedCamera</b>. A background thread reads continuously and stores only the newest frame with its capture time; read() waits for a frame newer than the last returned. "
                 "Stops reporting if the camera dies."],
                ["<b>tracker.py</b>", "<b>HandTracker</b>: MediaPipe Tasks API, hand landmarker in VIDEO mode (it tracks between frames instead of searching from scratch, which is faster). "
                 "<i>ensure_model</i> uses the bundled .task file; downloads only if it is missing (it never is in the installed version)."],
                ["<b>features.py</b>", "<b>normalize</b>: 21 landmarks to a feature vector independent of position, size and which hand it is (wrist at origin, divided by palm length, mirrored for the left hand)."],
                ["<b>poses.py</b>", "<b>RuleRecognizer</b> (hand-written geometry, no training) and <b>MLRecognizer</b> (a classifier you can train on your own recordings). Details in section 10. Thumbs-up, thumbs-down and the L shape (window commands) are recognised by this rule recogniser only."],
                ["<b>controller.py</b>", "the state machine: pose to action. Debounce, hold and release counts, relative cursor, acceleration, click snap-back, scroll with axis lock, window grab, drag, dropout grace. "
                 "No camera or OS calls in this file, so every behaviour is unit-tested."],
                ["<b>filters.py</b>", "<b>OneEuroFilter</b> and <b>PointFilter</b> (x and y): the adaptive smoothing described in section 10."],
                ["<b>attention.py</b>", "<b>Attention gate</b> (optional): gestures only while you face the screen. A 233 KB face detector (OpenCV YuNet) on a background thread estimates the head turn from the eye and nose landmarks; "
                 "<b>AttentionGate</b> decides, with a grace period, and is fully testable without a camera."],
                ["<b>gate.py</b>", "<b>AirGate</b>: in-the-air test plus asleep/awake state with the open-palm wake gesture."],
                ["<b>face_lock.py</b>", "<b>FaceLock</b> and <b>OpenCVFaceAnalyzer</b>: YuNet detects faces, SFace turns each into 128 numbers, cosine similarity decides. "
                 "Background thread. Also saving/loading the admin file and the (now unneeded in the installed version) model download helper."],
                ["<b>enroll_face.py</b>", "the enrolment window and command (18 samples, only when exactly one face is visible), <i>--add</i>, <i>--clear</i>, and <i>build_face_lock</i> which enrols on the first start and fails closed."],
                ["<b>screen.py</b>", "per-monitor DPI awareness, list of monitors (EnumDisplayMonitors), the combined desktop rectangle in physical pixels, screen ordering (main first, then left to right)."],
                ["<b>actions.py</b>", "mouse backends: <b>PynputMouse</b> (move, press, release, right click, vertical and horizontal scroll, read current position) and <b>NullMouse</b> (records, for tests and --dry-run)."],
                ["<b>windows.py</b>", "<b>Win32Mover</b>: window under the cursor via ctypes, restore if maximised, move with SetWindowPos; <b>NullMover</b> for tests."],
                ["<b>display.py</b>", "<b>Display</b>: shows the preview and reads keys on its own thread (imshow + waitKey cost 5-20 ms and used to stall the loop)."],
                ["<b>calibrate.py</b>", "records your own example of each pose (~80 samples each, about 5 minutes) to train a personal classifier. Optional."],
                ["<b>augment.py</b>", "adds simulated hand sizes, in-plane rotations, small tilts and noise to training data."],
                ["<b>train.py</b>", "trains and compares rule-based vs kNN vs MLP on your recordings; test on the last 30% of each recording or unseen sessions. Optional, needs scikit-learn (not in the installed version)."],
                ["<b>precision.py</b>", "measures cursor-point jitter (single knuckle vs the average of four) on the same frames; numbers in screen pixels."]], [32, 133])
    s += [P("Other files in the project folder", H3)]
    s += table([["Path", "Role"],
                ["config.yaml", "settings (section 6)"],
                ["run.bat", "development launcher: starts the app from the project's own Python environment and keeps the window open"],
                ["pyproject.toml", "package definition and dependencies: mediapipe, opencv-python, numpy, scikit-learn, joblib, pynput, pyyaml; dev: pytest"],
                ["tests\\", "139 automated tests in 10 files (section 15)"],
                ["models\\", "hand_landmarker.task and the two face .onnx models"],
                ["data\\", "admin_face.npz (your fingerprints), last_run.log"],
                ["archive\\multicam\\", "the removed multi-camera stereo code, tests and data (section 12, phase 8); not used by the app"],
                ["packaging\\", "everything that builds the installer and this guide (section 16)"]], [40, 125])

    s += [PageBreak(), P("10. The algorithms in detail", H1)]
    s += [P("10.1 Smoothing: the One-Euro filter", H2),
          P("Raw landmarks jitter by a pixel or two. A fixed smoothing filter must choose between steady-but-laggy and quick-but-shaky. The One-Euro filter "
            "adapts: its cut-off frequency is <font face='Courier'>min_cutoff + beta x speed</font>. At rest the cut-off is low (strong smoothing, so a trembling "
            "hand is calm); when the hand moves fast the cut-off rises (almost no smoothing, so no lag). A small dead zone makes the cursor ignore movement "
            "smaller than a few pixels."),
          P("Three presets (min_cutoff, beta, dead zone in pixels): smooth (0.5, 8, 5), balanced (1.0, 25, 4), responsive (1.5, 50, 3). The measured filter lag at slow speed "
            "is about 59, 28 and 17 ms. The assistant first set the smoothing too heavy (59 ms) in response to 'make it smooth', which later made the cursor feel laggy; "
            "this was measured in simulation and corrected by making 'responsive' the default.")]
    s += [P("10.2 Mouse-like (relative) movement", H2),
          P("Each frame the cursor moves by <i>gain x (change in hand position)</i>. The gain depends on the hand's speed through a smooth S-curve between "
            "<font face='Courier'>rel_gain_min</font> at <font face='Courier'>rel_v_low</font> and <font face='Courier'>rel_gain_max</font> at "
            "<font face='Courier'>rel_v_high</font> (curve in section 5). Extra rules make it feel like a real mouse:")]
    s += B(["A <b>soft dead zone</b> (rel_softness): movements smaller than 0.0003 of the picture per frame are tremor.",
            "A <b>glitch guard</b>: if the raw hand position jumps by more than 0.2 of the picture in one frame (tracking snapped to a different spot), the jump is "
            "ignored and the filter reset. The first version tested the guard after filtering, where it did nothing; it now tests the raw position.",
            "<b>Pointing 'lifts the mouse'</b>: the neutral pose pauses the cursor so you can reposition the hand.",
            "<b>OS-cursor resync</b>: the program remembers where it put the cursor. If Windows moved it (another mouse, or the cursor clamped by dead areas between screens of different sizes), "
            "it re-reads the real position instead of drifting."])
    s += [P("The first version of relative mode damped slow movement heavily for precision. In simulation the cursor then started moving 200 ms late and followed only "
            "34% of a slow hand movement, exactly what you described as 'I moved my hand really slowly, still lagging'. Raising the slow gain to 1.1, lowering the dead zone "
            "and the speed where acceleration begins brought this to 133 ms and 91% in the same simulation.")]
    s += [P("10.3 Which pose is it? (RuleRecognizer)", H2),
          P("Hand-written geometry, no training needed. For every finger it measures two things, each divided by palm length (wrist to middle knuckle) so that distance from the camera "
            "does not matter:")]
    s += B(["<b>Straightness</b> = straight-line distance from knuckle to fingertip / total length of the three bones along the finger. 1.0 is a perfectly straight finger. "
            "A straight finger looks straight from every angle, so this measure does not change when you turn your hand.",
            "<b>Reach</b> = fingertip-to-wrist distance / palm length. Short when a finger is folded toward the palm."])
    s += table([["Decision", "Rule"],
                ["Finger extended", "straightness >= 0.88 (stays extended down to 0.78 once it was extended: hysteresis, so it cannot flicker at the boundary)"],
                ["Finger curled", "straightness < 0.80, or (straightness < 0.88 and reach < 1.10)"],
                ["Anything in between", "unsure: counts as open palm (which can only move the cursor)"],
                ["Fist: to enter", "index, middle and ring all have reach < 1.10 AND straightness < 0.60"],
                ["Fist: to stay", "reach < 1.70 and straightness < 0.93 (sticky: only a clearly opened finger ends it)"],
                ["Pinch", "thumb tip to index tip distance / palm length below 0.25 to start, above 0.40 to stop (hysteresis)"],
                ["Open palm", "all four extended"],
                ["One finger", "index extended; middle, ring, pinky curled"],
                ["Two fingers (scroll)", "index + middle extended; ring + pinky curled (scroll stays through slight relaxing, but a relaxed hand does not start one)"],
                ["Three fingers (right)", "index + middle + ring extended; pinky curled"]], [38, 127])
    s += [P("An earlier version judged 'extended' by reach alone. Turning the hand shrinks the apparent length of every finger, and the pinky, the shortest, fell below the threshold "
            "first. Four open fingers then looked like three, which is the right-click pose. The new rule was checked with a simulated hand rotated up to 65 degrees in yaw and 60 in "
            "pitch: an open palm is now never read as right click at any of those angles (an automated test enforces it).", BODY)]
    s += [P("10.4 The controller state machine", H2),
          P("A pose must persist to count: 3 frames for click, right click and scroll, 2 for cursor movement, 5 for a fist (a window grab). Each of these exits only after the pose has "
            "really changed for 6 frames (click-drag) or 10 frames (window). A pose seen for the first time (the hand just appeared) may act immediately only if it is harmless "
            "(moving the cursor); clicks, scrolls and grabs always wait the full hold, which closed a hole found while testing the fist change. "
            "Short tracking dropouts of up to 0.3 s keep the held action alive.")]
    s += [P("Click snap-back: the controller keeps a short history of cursor positions. When the pinch is confirmed, the click is placed where the cursor was just before the pinch "
            "began (0.15 s earlier than the moment the pose first appeared), unless the cursor had travelled more than 100 pixels in that time.")]
    s += [P("10.5 Latency", H2),
          P("Measured on your PC: the camera delivers 30 frames per second (a 60 fps request gave 30 or even 20), so there is a floor of 33 ms between pictures, plus the webcam's own "
            "internal delay (exposure and USB) of roughly 50-100 ms that software cannot measure or remove. Finding the hand takes 8-9 ms. The on-screen figure is the software part. "
            "It ranged 15 to 31 ms: one frame in ten the preview drawing blocked the loop for 15-24 ms and the next camera picture had to wait. Moving the preview to its own thread fixed that.")]
    s += [P("10.6 Face lock", H2),
          P("YuNet finds faces in the picture; SFace converts each into a 128-number fingerprint. The fingerprint is compared with the enrolled ones by cosine similarity. "
            "A score of 0.363 or more counts as the administrator (this is the threshold the model's publisher recommends). The admin counts as present for 3 s after the last match. "
            "If a different face is the only one visible, or if no face is visible at all when <i>require_face</i> is on, hands are ignored. First-time enrolment is fail-closed: if nobody is enrolled, "
            "enrolment must finish or the app refuses to start.")]
    s += [P("10.7 Screens, DPI and windows", H2),
          P("The program declares itself per-monitor DPI aware so that Windows reports true pixels instead of scaled ones. It lists monitors with EnumDisplayMonitors and builds the virtual "
            "desktop rectangle (a monitor to the left or above the main one has negative coordinates). Relative cursor movement is clamped to that rectangle. A grabbed window moves via "
            "SetWindowPos (no resize, no z-order change, no activation); the window is the top-level ancestor of whatever is under the cursor, skipping the desktop and the taskbar.")]

    s += [P("10.8 Window commands", H2),
          P("Three more poses are added by the rule recogniser. The thumb counts as <i>out</i> when its four bones form a straight line (straightness 0.85 or more, like the fingers) and it reaches at least half a palm "
            "length from its base joint; a thumb whose joints coincide (a tracking dropout) is ignored. <b>Thumbs-up / thumbs-down</b>: thumb out, index, middle and ring clearly folded (the same fist test) and pinky bent, "
            "with the thumb within about 30 degrees of vertical (looser once held, 40 degrees, so it does not flicker); image y grows downwards, so a thumb tip above its base is up. "
            "<b>L</b>: thumb out, index extended, the other three bent, and 75 to 125 degrees between the thumb and the index finger, so a thumb merely held out while pointing does not count. "
            "None of the three can start while the last pose was a fist."),
          P("In the controller a command pose does not go through the click debounce. It runs its own timer: the pose must be on screen for 0.5 s (maximise, minimise) or 1.5 s (close). "
            "A flicker shorter than 0.15 s keeps the progress; any longer change cancels it. When the timer completes the command fires once on the window under the cursor and the pose must be left before it can fire again. "
            "While a command pose is shown the rest of the state machine sees a neutral pose, so the cursor stops at once. For 0.8 s after a command a fist cannot grab a window, and commands never start while a fist or pinch is held."),
          P("<b>Snapping.</b> While a window is held with a fist, the cursor's distance to the edge of the screen it is on (found with MonitorFromPoint, so it works on any screen) is checked every frame; inside the zone "
            "(30 pixels) a hint is shown. Opening the fist there snaps the window: the left or right half of that screen's work area (the screen minus the taskbar, adjusted for Windows' invisible resize borders), "
            "or maximise at the top edge. A corner counts as a side edge. Losing the hand never snaps. Close sends WM_CLOSE, the same message as the window's X button."),
          P("Measured on the simulated articulated hand (the same model as section 10.3, 300 noisy samples per case): facing the camera, none of the six existing poses was ever read as a command, and the three real commands "
            "were caught 99 to 100% of the time. Turned up to 20 degrees and rolled 15, thumbs-up and thumbs-down were caught 79% of the time (about a fifth of fists are already misread as open palm at that noise level, "
            "which is a property of the simulation) and the L 96%; at 35 degrees of turn at most 2.3% of pointing frames looked like an L. These are simulation numbers, not measurements on your hand.", SMALL)]

    s += [P("10.9 Attention gate", H2),
          P("Optional (<font face='Courier'>attention: enabled: true</font>). A small face detector (OpenCV's YuNet, 233 KB, on the CPU) finds faces about five times a second on a background thread, so the cursor is never delayed. "
            "The largest face is the user (anyone behind you is smaller). Its five landmarks give the head turn: the nose tip's offset from the midpoint of the eyes, measured along the line through the eyes (so a tilted head is not a turned head), "
            "divided by the distance between the eyes, equals about 0.476 x tan(turn) for an average head (about 30 mm of nose depth and 63 mm between the eyes). Facing the camera is 0 degrees."),
          P("The decision keeps the last time a face turned less than <b>max_turn_deg</b> (35) was seen. Gestures are allowed while that was within <b>grace_s</b> (1 s), so a glance at the keyboard or the phone does not interrupt a drag, "
            "and looking away for longer pauses everything; looking back resumes at once. With <b>require_face</b> on, no face in the picture counts as looking away. "
            "The camera window shows the live head turn ('facing the screen (turn 12 deg)'), which is also the way to tune max_turn_deg for your camera: it assumes the camera is on or near the screen you look at."),
          P("It does not identify anyone (that is the face lock) and stores nothing; pictures are used in memory for the check and dropped.", SMALL)]

    s += [PageBreak(), P("11. Privacy and safety", H1)]
    s += B(["<b>No picture ever leaves your computer.</b> The program never sends data anywhere. The only network code in it is a helper that downloads a model file if one is missing, and the installer includes all three models, so it does not run. Pictures live in memory for one frame.",
            "<b>No photos are saved.</b> The face lock stores 128 numbers per enrolment sample in data\\admin_face.npz. The hand model needs no personal data.",
            "<b>The log</b> (data\\last_run.log) contains poses, hold/release events and screen size, no pictures.",
            "<b>Uninstalling deletes your fingerprints.</b> You can also delete them any time with <font face='Courier'>enroll --clear</font>.",
            "<b>Gestures control a real mouse.</b> Start in try-it mode first; the hand-in-the-air rule, the one-second wake and the paused start exist so that stray motion does nothing.",
            "<b>The installer is not code-signed</b> and the program has not had a security review. Do not rely on the face lock to protect a computer from someone who has physical access to it."])
    return s
