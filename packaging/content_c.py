"""Part 3: history, side projects, limits, tests, packaging, roadmap, glossary."""
from reportlab.platypus import PageBreak

from pdf_lib import AMBER, BODY, B, H1, H2, H3, P, SMALL, callout, code, table


def phase(title, asked, found, did, status):
    return [P(title, H2),
            *table([["You asked / said", asked], ["What was wrong or learned", found], ["What was changed", did], ["How it was checked", status]],
                   [34, 131], header=False, zebra=False)]


def part3():
    s = []
    s += [PageBreak(), P("12. The full history: where it started and every change", H1)]
    s += [P("This is the story in order, from your own words. Each phase says what you asked, what was wrong, what changed and how that was checked. "
            "'Simulation' means a mathematical hand model, not your real hand. 'Confirmed by you' means you reported it working.")]
    s += table([["Phase", "Topic", "Tests after"], ["0", "Setting up the first project (gesture-mouse)", "53"], ["1", "Mood from the face; the ASL idea", "-"],
                ["2", "ASL fingerspelling project (separate)", "4"], ["3", "New project: gesture-control, first version", "9"],
                ["4", "Controls reshaped three times", "13 to 15"], ["5", "Smoothing, air gate, speed", "16 to 25"],
                ["6", "Drag cut-offs, lag measurement, multiple cursors question", "29 to 33"], ["7", "Scroll and right-click swap", "35"],
                ["8", "Two cameras, then removed", "56 to 66, back to 35"], ["9", "Mouse-like movement and latency", "44"],
                ["10", "Extra screens", "57"], ["11", "Precision, face lock, edge and line fixes", "61 to 78"], ["12", "Rotation and scroll-to-fist bugs", "80 to 83"],
                ["13", "Window commands discussed; this guide and the installer", "83"],
                ["14", "Choosing a name; the product becomes Hexra", "83"],
                ["15", "Window commands built: thumbs-up/down, L close, edge snap; the wave logo and window icons", "111"],
                ["16", "Accidental fist grabs fixed; no terminal window", "118"],
                ["17", "A fist no longer maximises: stricter thumbs-up, snap only when dragged into an edge", "121"],
                ["18", "Antivirus false positive: bootloader rebuilt from source", "121"],
                ["19", "My fist did not grab: the neutral thumb_fist guard removed", "121"],
                ["20", "Attention gate: only when you face the screen", "139"],
                ["21", "Settings app: every setting, with its latency", "167"],
                ["22", "One application: settings, live camera and controls in a single window", "173"],
                ["23", "Two cameras, fused", "196"],
                ["24", "Runs in the system tray", "199"],
                ["25", "Start with Windows", "202"],
                ["26", "Redesign: the Cockpit", "202"],
                ["27", "First-run hand calibration", "216"]], [18, 120, 27])

    s += phase("Phase 0: the starting point - gesture-mouse",
               "You shared a conversation and asked to read the project folder and complete its setup. After it was closed: 'tell me what to run'. "
               "Then: 'it is tracking both hands, but it is not moving the cursor or doing anything'.",
               "Installing from pyproject.toml failed with 'setup.py not found' because pip was too old. The newest pytest (9.2) crashed on Python 3.10.0. "
               "The 'does nothing' report was the safe --dry-run mode (it only tracks and draws), and otherwise the program needed to be engaged.",
               "Upgraded pip, installed the project into its own virtual environment, pinned pytest below 9 (8.4.2 works). All 53 tests passed. Run with: "
               "python -m gesture_mouse (real) or --dry-run (safe).",
               "Tests only; the webcam was not exercised by the assistant at that point.")
    s += phase("Phase 1: ideas that did not become this program",
               "'Can it understand my mood from my face?' and 'I want an app for deaf people ... braille ... ASL'.",
               "Mood: possible with MediaPipe's face landmarker (478 points and about 52 expression scores) but a weaker, more culturally variable signal than hands - decide the use first. "
               "Braille is a touch alphabet for blind people; the visual language for deaf people is ASL. Full conversational ASL is an open research problem (grammar uses the face, "
               "head, body and space), so fingerspelling A-Z came first.",
               "Nothing built for mood. ASL became its own project (next phase).",
               "Discussion only.")
    s += phase("Phase 2: asl-fingerspell (a separate project, still on disk)",
               "'Start with American'; 'only text for now'; 'use existing datasets'; 'tell me the space first'; 'it is not recognising properly'; "
               "'make it match my hand'; 'the letters move so fast, I do not know sign language'; 'will others need to train?'",
               "Public photos (Kaggle ASL Alphabet, 1.1 GB, one signer mostly) give landmarks via MediaPipe, but a model trained only on them scored 71.5% on your hand (kNN 55.1%). "
               "The first calibration ran too fast and showed no pictures.",
               "Built collect / calibrate / train / live / import_images. Downloaded the dataset only after your explicit approval (1.10 GB), extracted a subset with Python (tar could not read "
               "the zip), imported 22,473 landmark rows (1,000 per static letter), added augmentation, added skeleton drawing and an always-visible prediction to the live window, "
               "rebuilt calibration to show a reference photo per letter and wait for SPACE. Final model: public data plus 720 samples of your hand across 24 letters.",
               "The 100% held-out score after adding your hand was explicitly flagged as optimistic (held-out samples came from the same session). Training is a one-time step: "
               "other users receive the saved model file and only run live.")
    s += phase("Phase 3: the new project - gesture-control, first version",
               "'Leave this as a separate project; now create a new project that can control my screen.' Then: 'make closed fist move the tab, wherever I touch it should let me move the tab in front'.",
               "The original gesture-mouse project mixed concerns; screen control needed a clean state machine that can be tested without a camera.",
               "Created gesture-control: poses, controller, One-Euro filter, mouse and window backends, calibration and training tools, rule-based recogniser (works with no training), "
               "first config.yaml. First poses: index = cursor, pinch = click, thumb+middle pinch = right click, peace sign = scroll, fist = move the front window.",
               "9 then 13 tests. Windows window lookup checked read-only against your real screen. Not tried on your hand.")
    s += phase("Phase 4: controls reshaped three times",
               "'It is not moving the cursor' - 'WHAT ARE THE CONTROLS' - 'IT IS NOT WORKING PROPERLY' - 'pointing and right click are the same' - 'make the open palm the cursor, keep the earlier options' - "
               "'right click with two fingers, scroll was not working, and the fist should move the window under my cursor, not the front window'.",
               "(1) A real bug: the smoothing parameter beta had been set to 0.02 instead of the tuned 8.0 (carried over wrongly), so the cursor lagged until it looked frozen. "
               "(2) Thumb+middle pinch looked like pointing because a curled middle finger rests near the thumb. (3) 'Scroll by moving your hand' was not understood: it is movement, not a held position.",
               "beta fixed. Right click became a three-finger pose, then two-finger when you asked, and scrolling moved to follow-up requests. Open palm became the cursor pose; index finger became a neutral 'pause' pose. "
               "Fist now uses the window under the cursor (WindowFromPoint, top-level ancestor) instead of the foreground window. Unsure poses count as open palm so that a stray frame cannot grab a window.",
               "14 then 15 tests; cursor at (587, 690) correctly resolved to the terminal window, nothing moved.")
    s += phase("Phase 5: smoothing, the air gate and speed",
               "'Make the movements smooth, my hand might not be stable' - 'only access fingers when it is in the air, not when my head is resting' - 'increase response and speed to capture'.",
               "Shaky hands needed a stronger filter and a dead zone; resting hands needed to be ignored; and old camera frames pile up in a normal capture loop.",
               "Smoothing: min_cutoff 1.0 to 0.5, beta 8 to 4, 5-pixel dead zone, filtered scroll motion. Air gate: hand must be fully visible and in the upper part of the picture, plus asleep until a one-second open palm. "
               "ThreadedCamera keeps only the newest frame; the overlay shows real delay; harmless poses respond sooner.",
               "16 to 25 tests. Measured: your camera delivers 30 fps; hand finding takes ~8 ms; forcing 60 fps made it worse (20 fps). A 23 fps reading was a one-off.")
    s += phase("Phase 6: a drag that stopped, lag, and 'individual cursors'",
               "'I pinched and moved the tab, it moved fine, then it suddenly stopped in the middle even though I pinched' - 'it is lagging' - 'can I add individual cursors? If I cannot, do not do it, but check'.",
               "Four causes of the cut-off were fixed together: the air gate dropped the hand when it neared the bottom/edges; after one second the program fell asleep and a pinch cannot wake it; "
               "single misread frames ended the drag; very short tracking dropouts released it. My smoothing for 'smooth' was too heavy at 59 ms. "
               "Windows has exactly one system cursor, so real independent cursors are not possible on Windows 11 (they exist on Linux X11).",
               "Relaxed in-air check while holding; debounced release (6 frames); 0.3 s dropout grace; wake never needed during a hold; three feel presets; messages tell you why a drag ended. "
               "The experimental multi-cursor files were removed completely.",
               "29 then 33 tests. A config.yaml parse failure caught before shipping (a PowerShell BOM): the loader now reads utf-8-sig and tests cover it. Sweep simulations compared lag and jitter per preset.")
    s += phase("Phase 7: swapping scroll and right click",
               "'Flip right click and scrolling: two fingers open and others closed for scrolling left, right, top, bottom; three fingers for right click.'",
               "Scrolling had only been vertical.",
               "Two fingers = scroll in four directions with horizontal scroll support, axis lock (2.0) and gain 150; three fingers = right click.",
               "35 tests.")
    s += phase("Phase 8: two cameras (built, then removed)",
               "'Can I connect two cameras and use both?' -> 'I want stereo 3D, it should scan cameras, use as many as are connected' -> 'I have no printer' -> 'it can work automatically' -> "
               "'why only one camera in the end?' -> 'it stopped moving properly; remove it for now, I want to fix existing issues'.",
               "Stereo needs the cameras' relative positions. A checkerboard shown on a phone worked in a simulated test; automatic calibration from the hand also worked in simulation. "
               "On your two real cameras the set-up gave up after 15 s because the hand has to be visible to both cameras at the same moment, and the app silently fell back to one camera. The log showed the "
               "automatic set-up had worked once, but running both views together then stopped moving properly.",
               "Removed from the app at your request. The code, tests and data were moved (not deleted) to archive/multicam, which the app never touches. The README no longer mentions it.",
               "56 to 66 tests while it existed; back to 35 after removal; code search found no remaining references.")
    s += phase("Phase 9: 'just like a mouse', fast and accurate",
               "'I want the app to respond fast with my hand movement just like a mouse' - 'does USB-C reduce delay?' - 'how can I make it faster?' - 'it lags even when I move slowly' - 'it shows 15 to 31 ms'.",
               "A webcam cannot match a mouse: 33 ms between pictures plus a 50-100 ms internal delay that no software can remove. USB-C itself does not help (the version behind it can). "
               "My first relative mode over-damped slow movement (200 ms start, 34% follow). The 15-31 ms spread was the preview drawing stalling the loop one frame in ten.",
               "Relative mode with acceleration; responsive feel; optional 720p; better slow-speed gain; preview moved to its own thread.",
               "44 tests. Simulated: 133 ms and 91% follow after the fix. Preview-stall measured: 15-24 ms on 1 frame in 10 before, none after. Real-hand feel still needs your judgement.")
    s += phase("Phase 10: extended screens",
               "'What happens if I have an extended screen?' -> 'make it access it' -> 'I should be able to control on that screen as well'.",
               "The app read only the main screen size, so the cursor and windows could never reach another screen, and a screen to the left or above has negative coordinates.",
               "The whole virtual desktop is one area; per-monitor DPI awareness; config span/monitor options; window moves allowed into negative coordinates.",
               "57 tests including simulated two- and three-screen layouts (right, left, above, below, unequal sizes, L-shapes). Later your log showed a 6400 x 2160 combined desktop.")
    s += phase("Phase 11: precision, face lock, the yellow box and the blue line",
               "'The cursor lost track: I made a fist to move a tab, it released in the middle' - 'make precision better, I want it to work perfectly' - 'it should match only the admin face' - "
               "'why does it work only inside the yellow box?' - 'if the ball goes under the blue line, it does not work even when my hand is visible'.",
               "The log proved the program had not lost the hand: it read the fist as palm 6 times and as click twice. Perfect precision is impossible: landmark error is about a pixel or two. "
               "The yellow box limits nothing in relative mode; the real limits were the air gate's whole-hand-inside-the-picture rule and the blue line at 72%.",
               "Fist judged by fingertip reach with stickiness (stays a fist until a finger clearly opens); longer window-release; cursor follows the average of four knuckles; click snap-back; "
               "precision tool. Face lock built with OpenCV YuNet+SFace. edge_margin 0.02 to -0.15; blue line from 72% to 95% and now using the same point as the green circle.",
               "61 to 78 tests. Face lock: models downloaded only after you answered the y/N prompt; first attempt via github.com failed (SSL WRONG_VERSION_NUMBER; GitHub is unreachable from Python on your "
               "network), fixed by using Hugging Face; confirmed by you: 'it works great'.")
    s += phase("Phase 12: rotated hand = right click; scrolling fingers curl = fist",
               "'When I rotate my hand, why is it taking it as right click?' -> 'when I am scrolling top to bottom with two fingers, suddenly my fingers curled and it started to act as fist'.",
               "Rotation shrinks apparent finger length, so reach-based 'extended' failed first for the pinky. Separately, a fist was accepted for any merely bent fingers, so two scrolling fingers "
               "that relaxed became a fist and grabbed a window; and a pose seen on the very first frame could act immediately.",
               "Straightness-based finger test (section 10.3) with hysteresis; stricter fist (reach < 1.10 and straightness < 0.60 to enter); sticky scroll; grab needs 5 frames; "
               "click-type poses always wait the full hold, even as the first pose seen.",
               "80 then 83 tests. Sweeps over yaw -65..65 and pitch -60..60 show no open palm read as right click. Facing the camera, the stricter fist moved from about 60% to about 70% required curl. "
               "Remaining weak spots are in section 14.")
    s += phase("Phase 13: window commands (discussed) and this document",
               "'What are the best controls to close, minimise, enlarge, shrink and split the screen without overlapping?' -> 'fist already moves windows, won't it be misunderstood, and the controls seem small'.",
               "A left-hand fist for 'close' would depend on MediaPipe always labelling hands correctly (it sometimes swaps them) and would collide with the grab fist. "
               "So no pose may be reused, and anything destructive needs a pose nothing else uses.",
               "Not built yet. Proposed in section 17. Instead, this guide and a single-file installer were produced.",
               "Design discussion; the installer was built and self-tested (section 16).")
    s += phase("Phase 14: a name and a brand - Hexra",
               "You wanted a unique name that starts with H, then said it should reflect two hands and fingers, then control rather than projection, and finally that you want a short brand name. Final choice: <b>Hexra</b>, tagline <b>Your hands, in control</b>.",
               "Names were checked on PyPI, npm and crates.io, GitHub (repo names, accounts, descriptions) and the web, including trademark aggregator sites. Rejected for real conflicts: HoloTouch (a holographic-touch company with trademarks), HaloTouch (a CHI 2025 research system and several Halo Touch products), HeliosTouch (a Helios Touch LLC trademark), Helm (the Kubernetes tool), Harmony (Logitech and Huawei marks), Hico and Haco (research benchmarks, software companies, taken packages). Hexra had no registry, GitHub or web match; the nearest is a puzzle game called Hexara. It is a coined word with no meaning of its own, which is why it is ownable; the tagline carries the meaning.",
               "The program, installer, shortcuts, window title, Python package (hexra), settings comments, tests, this guide and the GitHub repository were renamed. The folder on disk is still called gesture-control.",
               "All 83 tests pass after the rename; the installer was rebuilt and self-tested. Not done: a USPTO trademark search, a registrar check for domains and social handles. Do both before treating Hexra as a registered brand.")
    s += phase("Phase 15: window commands",
               "'Build the window commands next.' (the design from phase 13: no pose shared between a command and a movement; close must be hard to trigger by accident).",
               "Thumbs-up, thumbs-down and an L shape needed thumb detection, which did not exist. A first version read the simulated pointing hand as an L 95% of the time, because geometry alone cannot separate a thumb held out from an intentional L; "
               "the L angle window was raised to 75 to 125 degrees. A held thumbs-up fired again after its cooldown, and the cursor moved for the first frame of a command pose; both were caught by tests and fixed.",
               "Three new poses in the rule recogniser; timed one-shot commands in the controller (0.5 s, close 1.5 s with a progress ring; cancel on dropping the pose; fire once; no cursor movement; no fist grab for 0.8 s after a command); "
               "edge snapping of a fist-dragged window with a live hint; Win32 maximise, minimise, close (WM_CLOSE) and monitor-aware half-screen snapping; config keys and documentation.",
               "109 tests (26 new). Simulation: frontal hand read as a command by mistake 0% of the time; commands caught 99 to 100% frontal, about 79 to 96% turned 20 degrees. "
               "Not done: a test on your real hand, and a live test of the Win32 calls on real windows (only the lookups were smoke-tested).")
    s += phase("Phase 16: accidental fist grabs, and no terminal window",
               "After testing the window commands: 18 window grabs started and ended in three minutes while trying thumbs poses. Then: 'it opens terminal and the tab as well, can I make it run just the tab', and 'fix the accidental fist grabs'.",
               "A thumbs-up is made by closing the fingers into a fist and then raising the thumb, and a fist held for about 0.17 s was a window grab. Worse, a fist stuck (the recogniser never reported the thumb after a fist), "
               "and a grab had real side effects at once: it un-maximised a maximised window and then followed every wobble of the hand. In a simulation of 200 thumbs-ups the old behaviour started a grab 100% of the time, moved a window 98% of the time and fired the command 0% of the time.",
               "Three layers. (1) The grab is deferred: a fist only takes hold of a window after the hand has moved 30 pixels, and then follows from where the fist started; a still fist touches nothing. "
               "(2) The recogniser reports a thumbs pose even right after a fist, a fist with a rising thumb is neutral, and a thumbs pose before any window is held cancels the pending grab, while a window really being dragged is never dropped by a thumb. "
               "(3) After any thumbs pose a fist cannot grab for 0.6 s. Separately, the installed program is now a windowed program with no terminal; a console opens only for uninstall, selftest, enroll and precision, and problems appear in a message box.",
               "118 tests (7 new, 3 rewritten). Same simulation after the fix: a grab started in 0.5%, a window moved in 0.5%, the command fired in 83% (limited by simulated holds shorter than 0.5 s). "
               "The windowed build was checked in a temporary copy: self-test passed, one visible window (the camera window), no console. Not tested on your real hand.")
    s += phase("Phase 17: 'the fist is maximising the tab'",
               "After testing 1.1.3 on a real hand: 'the fist is maximising the tab'.",
               "Two causes were plausible from the log. (1) A thumbs-up was recognised for any straight, upright thumb, and a thumb simply resting along a fist is straight and upright too, so an ordinary fist could read as a thumbs-up and maximise after 0.5 s. "
               "(2) Window title bars sit within 30 pixels of the top of the screen, so grabbing a window by its title bar and letting go there counted as dragging it to the top edge, which maximises. The log could not tell the two apart, because both print 'maximised'.",
               "A thumbs-up now has to stick out beyond the fist (its tip at least 1.3 palm lengths along the hand's axis, so 1.15 once held); a thumbs-down has to point below the wrist. A thumb resting on a fist is now a neutral pose and does nothing. "
               "A snap only counts if the cursor was away from the edge at some point during the drag (a window that starts at the edge and is let go there does not snap, and no hint is shown). "
               "Log lines now say what fired: the pose in brackets for a command, '[snap top]' for a snap, and 'snapped to the top (maximised)'.",
               "121 tests (3 new). Simulation, 300 samples each: a fist with a thumb resting along it was read as a thumbs-up 0% of the time; real thumbs-ups caught 100% facing the camera, 79% turned 20 degrees. "
               "Not tested on your real hand: this is a fix for two likely causes, not a confirmed diagnosis.")
    s += phase("Phase 18: Windows Security removes Hexra.exe",
               "Windows Security twice removed the installed Hexra.exe (and its shortcuts) as Trojan:Win32/Bearfoos.A!ml. You asked: 'rebuild the launcher from source'.",
               "!ml is a machine-learning guess, typical for new unsigned programs built with PyInstaller. Every PyInstaller program carries the same stock bootloader, a small launcher that many antivirus engines treat with suspicion. "
               "It was not caught by a scan on install, but about five minutes after the program first ran (the cloud check), once at the first run and once mid-session. Nothing was found wrong with the program itself.",
               "Your PC had no C compiler, so with your approval I downloaded w64devkit (a portable MinGW-w64 gcc 16.2, 65.6 MB from github.com/skeeto/w64devkit, checked against the sha256 GitHub publishes) and PyInstaller's own source (4.2 MB from PyPI, hash checked), "
               "built the 64-bit bootloader (run, runw and their debug versions) and installed it into the build environment, keeping the originals. The new bootloader is a different binary (192 KB against 307 KB). "
               "The steps are in packaging/build_bootloader.ps1; the compiler is in packaging/toolchain, which is not in git.",
               "The rebuilt program was tested in a temporary copy (self-test, one window, no console). Whether Windows Security accepts it is only known after real use: this is a common mitigation, not a guarantee. See the results in the release notes.")
    s += phase("Phase 19: 'why is my application not working'",
               "'Why is my application not working', right after installing 1.1.4.",
               "Two things. (1) The running copy had been started with --dry-run, which is the 'try it, mouse untouched' shortcut: in that mode Hexra shows poses but never moves the mouse or a window. "
               "(2) The log showed 'pose changed to thumb_fist' again and again: the guard added in phase 16 made any fist whose thumb was straight and fairly upright a neutral pose, and this user's ordinary fist is exactly that, so it could not grab a window. "
               "In simulation about 8% of fists at a heavy turn were affected; on a real hand it was far more. I had flagged it as a risk and it was real.",
               "The guard is removed: a fist is a fist whatever its thumb does. Accidental grabs are still prevented by the deferred grab (a fist only takes hold of a window once the hand moves 30 pixels) and by the guard after thumbs poses; "
               "a thumbs-up still has to stick out beyond the fist. The installer exe is now also built with the custom bootloader.",
               "121 tests (the thumb_fist tests rewritten to expect an ordinary fist).")
    s += phase("Phase 20: only when I see the screen",
               "'Can I make this work only when I see the screen, and not when I am talking to my friend, facing my face away from my screen.'",
               "Hexra only looked at the hand, so it kept obeying while you turned away. Hexra already carried a small face detector (for the face lock) that gives eye and nose landmarks, which is all a head-turn estimate needs.",
               "A new optional attention gate (attention.py): a 233 KB YuNet face detector on a background thread, the head turn from the nose offset between the eyes (about 0.476 x tan(turn)), "
               "gestures paused once you have looked more than 35 degrees away (or no face is seen) for more than 1 second, resumed the moment you look back. The camera window shows the live turn and LOOKING AWAY. "
               "Off by default; the detector model ships in the installer; the self-test loads it.",
               "139 tests (18 new), all with a fake detector and no camera. The 0.476 constant is average anatomy, not calibrated on your face: the live number in the camera window is how to tune max_turn_deg. Not tested on your real face yet.")
    s += phase("Phase 21: a settings app",
               "'Prepare an application style and let users change settings, like everything, and mention the possible latency for each option... like Notewll has.'",
               "Every behaviour lived in a commented config.yaml. Fine for me, hard for anyone else, and nothing said what a choice costs in speed.",
               "Hexra Settings: a local window (Start Menu, or Hexra.exe settings) in the Notewll style. settings_schema.py lists every setting with range, default, explanation and a latency note "
               "(frames become milliseconds at 30 fps; presets carry measured filter lag; each note says whether it was measured, simulated, calculated or estimated). config_io.py edits config.yaml line by line so comments survive, re-reads the result before writing and keeps config.yaml.bak. "
               "settings_app.py serves it on 127.0.0.1 only, with a secret token and Host check, and quits when the window closes.",
               "167 tests (28 new): the catalogue covers every config key, every setting round-trips through the real config and the app loads it, bad input changes nothing, the server refuses requests without the token.")
    s += phase("Phase 22: one application",
               "'I want single application: when I press Hexra it should open a single page, the settings place, and the camera that it is showing right now, positioned in the sidebar.'",
               "Hexra was two things: a settings window and a separate OpenCV camera window, each started its own way.",
               "Pressing Hexra now opens one window. The camera picture is in the sidebar with Start / Stop, Pause / Resume and a try-it switch; the settings are the pages beside it. "
               "The control engine still runs as its own process (a camera or tracker problem cannot take the window down); it leaves the newest picture and its status in data\\ (ipc.py) and the window streams the picture as motion-JPEG. "
               "Saving a setting restarts the engine so it takes effect at once; closing the window stops the engine, so nothing keeps controlling the mouse out of sight.",
               "173 tests (6 new) with a stand-in engine that speaks the same protocol; the real engine was also run end to end in try-it mode with the real webcam.")
    s += phase("Phase 23: two cameras again, fused",
               "'When it has multiple cameras the straight face should be disabled, and both should scan and track my fingers with precision, they should integrate the tracking.' -> "
               "'I want the fused setup' -> 'which camera has the better view, it should take that input'.",
               "The first two-camera version (phase 8) tried true stereo 3D and failed on the real cameras: set-up needed both cameras to see the hand at once, then it stopped moving properly.",
               "No 3D and no set-up step. Each camera runs its own tracker on its own thread; the loop is paced by camera 1 so every frame-count setting keeps its meaning. fusion.py learns an affine map camera 2 -> camera 1 from moments when both see the hand, "
               "then averages the cursor point weighted by view quality (detector confidence x how much of the hand is inside the picture x how large it is). The pose and finger shape come from the better view only, with hysteresis. "
               "If a camera loses the hand the other carries on with no jump (an offset keeps the point continuous); if the two views stop agreeing the map is thrown away and relearned. "
               "The mode (fused, camera 1 only, camera 2 only, learning N%) is shown in the sidebar, so nothing falls back silently. The face-direction gate is switched off with two cameras. The Camera page detects cameras and shows a picture of each.",
               "196 tests (23 new): learning the map, fused noise lower than a single camera, failover without jumps, the better view, a bumped camera, and the two-camera source with fake cameras. "
               "NOT yet tried on two real cameras: this machine currently shows one webcam and one infrared webcam, so the real-hardware behaviour is unverified.")
    s += phase("Phase 24: keep running in the system tray",
               "'I want this app running in background as well, even if I close this application it should be running in the tray bar; only if they close from the system tray it should close.'",
               "Closing the window used to end Hexra, because the window was the application.",
               "Hexra now has a tray icon (tray.py, plain Windows calls, no extra library). Closing the window leaves Hexra, and the engine if it was running, going. Left-click the icon (or start Hexra again, which finds the running copy and just shows its window) to bring the window back; "
               "right-click for Open, Pause / Resume, Start / Stop and Quit. Quit is the only way to close it: it stops the engine, removes the icon and closes the window. "
               "If a tray icon cannot be made, closing the window still ends Hexra, so it is never left running with no way to close it.",
               "199 tests (3 new) really add and remove a tray icon and send it clicks and menu commands. The whole close-the-window / reopen / quit cycle is checked on the installed copy.")
    s += phase("Phase 25: start with Windows",
               "'Make it start with Windows.'",
               "Hexra lived in the tray but still had to be started by hand after every restart.",
               "A toggle on the Overview page writes one value to the current user's Run key (autostart.py, no administrator rights): Hexra --background, which goes straight to the tray with no window. "
               "A separate setting, Start hand control automatically (Startup page, off by default), also switches the camera and control on at launch. Uninstalling removes the entry. "
               "If a tray icon cannot be made the window still opens, so Hexra is never invisible at login.",
               "202 tests (3 new, using their own registry key, never the real Run key).")
    s += phase("Phase 26: redesign with 21st.dev",
               "'Can you redesign the application using the 21st.dev connector?' -> three directions were shown -> 'A: Cockpit'.",
               "The window was a light sidebar app with the camera squeezed into the sidebar. When tuning a setting you want to watch your hand, not a thumbnail.",
               "21st.dev was searched for settings, dashboard and command-palette references (its AI generation is not enabled on the plan, so the previews were built by hand from those references). "
               "Three directions were compared (Cockpit, Calm, Board) and you chose the Cockpit: a dark window with the tabs along the top, the camera as a large stage on the left with the status on it (Controlling, pose, fps, fused), "
               "and the settings as an inspector on the right. Nothing was removed: every page, setting, preset, the tray and start-with-Windows are the same.",
               "202 tests; only the look changed (index.html, app.css and the tab labels in app.js). Checked in screenshots of the real app on the Overview, Cursor and Camera pages.")
    s += phase("Phase 27: calibrate to your own hand",
               "'It is confusing: I made a fist and it thought I was giving thumbs-up, and the other way round.' -> a pose check with your hand -> 'It did not work properly, make this calibration when they first install.'",
               "A pose check on your real hand showed your fist rests with the thumb tucked against the index finger, which the rules call a pinch (a click); a thumbs-up turned a little looks like a fist. The rules are written for an average hand.",
               "The first time Hexra opens it walks you through nine poses (open palm, fist, thumbs-up, thumbs-down, pinch, one, two and three fingers, L): a 3-second get-ready and a 6-second hold each, asking you to turn your hand a little. "
               "handfeat.py describes each frame as 19 size-independent numbers (finger straightness and reach, many thumb measures including 3D). personal.py classifies by the nearest of YOUR recorded examples (numpy, no extra library), "
               "falls back to the rules for anything unfamiliar, smooths over 3 frames, and cross-validates on blocks of its own recording so it can tell you which poses your hand makes look alike. "
               "The first moments of each hold and stray frames are discarded; a pose with no hand is asked again, twice, then skipped. The result is saved to data/calibration.npz and used from then on (switch: Use my hand calibration). "
               "Also fixed on the way: a refused request could reset the connection (the unread request body), which caused an occasional failing test.",
               "216 tests (14 new) with synthetic hands: each pose separates when turned 20 degrees; a fist whose thumb touches the index is a fist for this hand though the rules call it a click; look-alike poses are reported. The walk-through itself still needs you at the camera.")

    s += [PageBreak(), P("13. The other projects on your PC", H1)]
    s += table([["Folder", "What it is", "Status"],
                ["hexra (this folder was called gesture-control)", "this program", "active"],
                ["gesture-mouse", "the original single-hand mouse project that gesture-control grew from", "kept as it was; set up in phase 0"],
                ["asl-fingerspell", "ASL alphabet recogniser (collect, calibrate, train, live, import_images)", "separate; trained with the Kaggle data plus your hand"],
                ["asl-dataset", "the extracted subset of the Kaggle ASL Alphabet images", "can be deleted once the model is trained"],
                ["archive (1).zip", "the 1.1 GB Kaggle download", "can be deleted; the landmarks are already extracted"],
                ["gesture-control\\archive\\multicam", "the removed stereo code, tests and data", "not used by the app"]], [48, 82, 35])

    s += [P("14. Known limits - read this before trusting it", H1)]
    s += B(["<b>Webcam delay.</b> 30 fps and 50-100 ms of internal camera delay are hardware limits. The software part is 15-31 ms or less. It cannot feel exactly like a mouse.",
            "<b>Precision.</b> Hand landmarks carry about a pixel or two of error; filtering reduces shake but cannot make it perfect.",
            "<b>Tested in simulation.</b> The rotation, curl, jitter, lag and click-drift fixes were validated with simulated hands. Only the face lock, the basic operation and several fixes were reported working by you.",
            "<b>Turned fists.</b> A fist turned sideways to the camera was not recognised in the simulation. A scroll hand tilted backwards was not detected in the simulation.",
            "<b>Face lock is a convenience lock.</b> A photo or video of you can fool it; it checks a face, not whose hand it is.",
            "<b>One hand at a time</b> is used for control (the first one found). Two-hand commands are not built.",
            "<b>Window commands are new and untested on a real hand.</b> A thumb held out while pointing can look like an L, so close needs a 1.5 s hold and shows a ring. They need the rule recogniser (the default); a personally trained classifier does not produce the thumb poses.",
            "<b>One camera</b> (camera 0). The multi-camera work is archived.",
            "<b>Windows only.</b> The window mover and the DPI and monitor code use Windows APIs.",
            "<b>The window mover</b> cannot move windows of programs running as administrator, because Windows blocks it.",
            "<b>Unsigned installer.</b> Windows SmartScreen and some antivirus programs will warn."])

    s += [P("15. Tests", H1)]
    s += [P("216 automated tests, run with <font face='Courier'>.venv\\Scripts\\python -m pytest</font>. They need no camera: the controller, the recogniser and the "
            "filters take plain numbers.")]
    s += table([["File", "Tests", "What it checks"],
                ["test_control.py", "32", "debounce; moving poses start within 2 frames and clicks need the full hold; drag survives flicker and short dropout, ends after sustained release or long loss; "
                 "right click once per entry; scroll in all four directions and diagonal; shaky hand stays put; fist grab, window follows the hand, drop on open palm or lost hand; "
                 "ambiguous hand never grabs; sticky fist; pinch hysteresis; open palm never right click at any tested yaw/pitch; scroll curl does not become a fist; grab needs 5 frames"],
                ["test_relative.py", "9", "cursor starts from the real position without a jump; fast movement goes farther than slow; pointing lifts the mouse without a jump; a click lands where the cursor is; "
                 "a tracking glitch does not fling the cursor; stays on screen; tremor barely moves it; dragging a window moves it by the cursor change; absolute mode unchanged"],
                ["test_precision.py", "6", "the four-knuckle average ignores a one-landmark wobble and a pinch-time knuckle shift; a click lands where you aimed, not where the pinch pushed the hand; "
                 "no snap-back while really moving; right click also lands on target; absolute mode unaffected"],
                ["test_screens.py", "13", "single screen unchanged; second screen right, left (negative coordinates), above; three screens; primary-only and single-screen choice; bad screen number and manual override; "
                 "this PC's real screens; absolute and relative cursor reach both edges; the dead area between unequal screens does not trap the cursor; default config describes the whole desktop"],
                ["test_face_lock.py", "9", "admin accepted and stranger rejected; nobody in view is locked; grace period then lock; a stranger alone never unlocks; admin with a stranger beside is allowed; "
                 "lenient mode; similar-but-different people; rate-limited threaded checks never block; enrolment file holds only numbers"],
                ["test_gate.py", "10", "starts asleep; wakes after an open palm in the air; a resting low hand never wakes; a hand cut off by the frame edge is not in the air; a brief wobble resets the wake timer; "
                 "lowering the hand sleeps; disabled gate passes everything; reaching low or to the edge while dragging does not drop; negative edge margin; the line uses the same point as the ball"],
                ["test_commands.py", "26", "thumbs-up, thumbs-down and L are recognised; an ordinary fist (thumb tucked, to the side or diagonal) never is; pointing is not an L; a thumb out of a held fist is ignored; "
                 "tilt tolerance and no flicker; a command fires once after its hold, again only after leaving the pose; close needs 1.5 s and shows progress; dropping the pose cancels; a flicker keeps progress; "
                 "the cursor does not move during a command; no command while a fist is held; no grab right after a command; remapping works; edge zones, left/right/top snap, corners, live hint, no snap when the hand is lost or snapping is off, snap uses the screen under the cursor"],
                ["test_commands.py (grab tests)", "6", "a fist that stays still takes hold of nothing; a fist on its way to a thumbs-up is not a grab; a moving fist takes hold and follows from where it started; "
                 "a window really being dragged is not dropped by a thumb popping out; relaxing out of a thumbs pose does not grab; an ordinary deliberate grab still works"],
                ["test_attention.py", "18", "the head-turn estimate (0 facing, follows the real turn, left = right, a tilted head is not a turned head, face size irrelevant, a degenerate face is away); the biggest face is the user; "
                 "the gate (waits for the first check, glances do not interrupt, longer looking away pauses and looking back resumes, configurable limit, no-face rules); the thread wrapper with a fake detector (rate limit, a failing detector does not crash, never blocks); off by default"],
                ["test_icon.py", "2", "the icon file is found; setting the window and taskbar icon never raises, whatever the window or platform"],
                ["test_config.py", "4", "shipped config loads; a file with a byte-order mark loads; explicit values override the preset; unknown feel is rejected"]], [32, 12, 121])

    s += [PageBreak(), P("16. Building the installer and this guide", H1)]
    s += [P("Everything is in the <font face='Courier'>packaging</font> folder of the project. The method was chosen so that nothing extra has to be downloaded or installed "
            "on the target PC and no third-party installer toolkit is needed: the installer is itself a small Python program (tkinter wizard) packaged by PyInstaller.")]
    s += table([["File", "Role"],
                ["launcher.py", "entry point of Hexra.exe: sets the working folder to the install folder, runs the app with the rule recogniser, or enroll / precision / selftest / uninstall. "
                 "Gives mediapipe empty stand-ins for matplotlib (which the program never uses) so that matplotlib can be left out."],
                ["build_app.ps1", "PyInstaller command (run from the slim environment packaging/buildenv: mediapipe + plain opencv-python without the contrib extras, which only the face recogniser needed; the 30 MB video-file decoder is deleted because a webcam does not use it): console program, mediapipe collected in full, scikit-learn, scipy, pandas, pytest, matplotlib and PIL excluded"],
                ["installer.py", "the wizard: folder choice, shortcuts, progress bar; silent mode /S /DIR= /NOSHORTCUTS; writes the uninstall entry in HKCU; keeps an existing config.yaml"],
                ["make_icons.py", "builds the logo files and app.ico from assets/logo-hand-cursor-master.png, preserving transparency"],
                ["pdf_lib.py, content_*.py, make_pdf.py", "this document"],
                ["build_bootloader.ps1", "rebuilds PyInstaller's bootloader (the small launcher inside Hexra.exe) from source with a portable MinGW-w64 gcc (w64devkit, checked against GitHub's published sha256) and installs it into packaging/buildenv. "
                 "The compiler (about 700 MB) lives in packaging/toolchain, which is not in git"],
                ["build_all.ps1", "runs: build app, stage models and config, make the PDF, zip the payload, build the single-file installer"]], [48, 117])
    s += [P("Rebuild", H3), code("cd <the project folder>\npowershell -ExecutionPolicy Bypass -File packaging\\build_all.ps1"),
          P("Result: <font face='Courier'>packaging\\Hexra-Setup.exe</font> and <font face='Courier'>packaging\\Hexra-Guide.pdf</font>.")]
    s += [P("What was deliberately left out of the installer", H3)]
    s += B(["<b>Your enrolled face</b> (data\\admin_face.npz). Fingerprints of your face are personal; every installation enrols its own administrator.",
            "Your logs, your edited config (a clean default config.yaml is shipped), the training tools' dependencies (scikit-learn, joblib), the archived multi-camera work and the tests."])
    s += [P("Verification done on the packaged program", H3)]
    s += B(["The packaged Hexra.exe was run with <font face='Courier'>selftest</font>: config loads, the hand tracker loads and runs on an empty picture, both face models load, "
            "the recogniser and controller import.",
            "The installer was run silently into a temporary folder and the result was checked (files, shortcuts, uninstall entry) and then removed.",
            "The installed program was started with <font face='Courier'>--dry-run --no-face-lock</font> for 12 seconds: the camera opened and the loop ran without errors. "
            "Uninstall was run and removed the folder, shortcuts and registry entry.",
            "<b>Not verified:</b> tracking a real hand and the face enrolment from the packaged exe (no hand was in view during the 12-second run), and the visual wizard window on a clean second PC "
            "(only the silent install path was exercised)."])

    s += [P("17. Where it could go next", H1)]
    s += [P("Window commands are now built (section 4, 10.8 and phase 15). The design principle stays: <b>no pose is shared between two commands</b>, and destructive commands need a pose nothing else uses.", BODY)]
    s += table([["Idea", "Status", "Notes"],
                ["Split screen left / right", "built", "drag with a fist to the left or right edge and open the hand"],
                ["Maximise / restore", "built", "thumbs-up held 0.5 s, or drag to the top edge"],
                ["Minimise", "built", "thumbs-down held 0.5 s"],
                ["Close", "built", "L shape held 1.5 s with a ring; same as the X button"],
                ["Quarter-screen snapping", "idea", "corners; today a corner counts as a side"],
                ["Enlarge / shrink", "idea", "two hands pinching apart / together; needs two-hand tracking and reliable hand labels"],
                ["Face lock in the installer", "idea", "it is in the source, off in the installer build"]], [50, 22, 93])
    s += [P("You said the controls 'seem small'; if that meant too few controls, nine poses are now available, but each extra pose raises the chance of confusion; "
            "if it meant on-screen size, the overlay text and the camera window can be enlarged.")]

    s += [P("Glossary", H2)]
    s += table([["Term", "Meaning"],
                ["Landmark", "one of 21 numbered points MediaPipe finds on a hand"],
                ["Pose", "a hand shape the program names: palm, point, click, right, scroll, fist"],
                ["Debounce", "requiring a pose to persist for several frames before acting on it"],
                ["Hysteresis", "different thresholds to enter and to leave a state so it cannot flicker at the boundary"],
                ["One-Euro filter", "adaptive smoothing: strong when still, weak when moving fast"],
                ["Relative mode", "cursor moves by hand movement with acceleration, like a mouse"],
                ["Air gate", "the rule that the hand must be raised in the air and the program awake"],
                ["Face lock", "gestures work only while the enrolled administrator's face is recognised"],
                ["Embedding / fingerprint", "128 numbers describing a face; not an image"],
                ["DPI awareness", "telling Windows the program uses true pixels so coordinates are not scaled"],
                ["Dry run", "mode that tracks and shows poses without touching the mouse or windows"],
                ["PyInstaller", "tool that packs Python programs and their libraries into an .exe"]], [38, 127])
    return s
