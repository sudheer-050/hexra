"""Attention gate: gestures only while a face is turned toward the screen."""
import math

import numpy as np

from hexra.attention import DEFAULTS, NOSE_PROTRUSION, Attention, AttentionGate, largest_face, turn_degrees


def face(turn_deg=0.0, eye_dist=60.0, cx=300.0, cy=200.0, size=None, tilt_deg=0.0):
    """A YuNet row for a head turned `turn_deg`: the nose tip sits NOSE_PROTRUSION * tan(turn) eye-distances off the eye midpoint."""
    a = math.radians(tilt_deg)
    ux, uy = math.cos(a), math.sin(a)                                   # direction along the line through the eyes
    off = NOSE_PROTRUSION * math.tan(math.radians(turn_deg)) * eye_dist
    rex, rey = cx - ux * eye_dist / 2, cy - uy * eye_dist / 2
    lex, ley = cx + ux * eye_dist / 2, cy + uy * eye_dist / 2
    nx, ny = cx + ux * off - uy * 25, cy + uy * off + ux * 25            # the nose is a little below the eyes (perpendicular to the eye line)
    w = size or eye_dist * 2.2
    return np.array([cx - w / 2, cy - w / 2, w, w, rex, rey, lex, ley, nx, ny, 0, 0, 0, 0, 0.95], dtype=np.float32)


# ---------------------------------------------------------------- the head-turn estimate
def test_a_face_looking_at_the_camera_has_no_turn():
    assert turn_degrees(face(0)) < 1.0


def test_the_turn_estimate_follows_the_real_turn():
    for deg in (10, 20, 30, 45, 60):
        assert abs(turn_degrees(face(deg)) - deg) < 1.0, deg


def test_turning_left_or_right_gives_the_same_amount():
    assert abs(turn_degrees(face(35)) - turn_degrees(face(-35))) < 0.01


def test_a_tilted_head_is_not_a_turned_head():
    assert abs(turn_degrees(face(0, tilt_deg=25))) < 1.0
    assert abs(turn_degrees(face(30, tilt_deg=25)) - 30) < 1.0


def test_the_size_of_the_face_does_not_matter():
    assert abs(turn_degrees(face(30, eye_dist=25)) - turn_degrees(face(30, eye_dist=120))) < 0.01


def test_a_degenerate_face_counts_as_turned_away():
    assert turn_degrees(face(0, eye_dist=0.0)) == 90.0


def test_the_biggest_face_is_the_user_not_the_friend_behind():
    near, far = face(5, eye_dist=70), face(60, eye_dist=25, cx=500)
    assert largest_face(np.stack([far, near])) is not None
    assert abs(turn_degrees(largest_face(np.stack([far, near]))) - 5) < 1.0
    assert largest_face(None) is None and largest_face(np.zeros((0, 15))) is None


# ---------------------------------------------------------------- the decision
def test_gestures_wait_for_the_first_face_check():
    g = AttentionGate()
    assert not g.allowed(0.0)
    g.update(5.0, 0.1)
    assert g.allowed(0.1)


def test_facing_the_screen_allows_gestures_continuously():
    g = AttentionGate(max_turn_deg=35, grace_s=1.0)
    for i in range(50):
        g.update(10.0, i * 0.2)
        assert g.allowed(i * 0.2)


def test_a_quick_glance_away_does_not_interrupt():
    g = AttentionGate(max_turn_deg=35, grace_s=1.0)
    g.update(5.0, 0.0)
    for i in range(1, 4):                                                # 0.6 s looking at the phone
        g.update(70.0, i * 0.2)
        assert g.allowed(i * 0.2)
    g.update(5.0, 0.8)
    assert g.allowed(0.8) and g.allowed(1.5)


def test_looking_away_for_longer_pauses_gestures_and_looking_back_resumes_them():
    g = AttentionGate(max_turn_deg=35, grace_s=1.0)
    g.update(5.0, 0.0)
    t = 0.0
    while t < 2.0:
        t += 0.2
        g.update(60.0, t)
    assert not g.allowed(t)                                              # talking to a friend for 2 s
    g.update(8.0, t + 0.2)
    assert g.allowed(t + 0.2)                                            # back to the screen


def test_the_limit_is_configurable():
    strict, loose = AttentionGate(max_turn_deg=20, grace_s=0.0), AttentionGate(max_turn_deg=50, grace_s=0.0)
    for g in (strict, loose):
        g.update(30.0, 1.0)
    assert not strict.allowed(1.5) and loose.allowed(1.0)


def test_no_face_counts_as_looking_away_by_default_but_not_when_asked():
    g = AttentionGate(grace_s=1.0, require_face=True)
    g.update(5.0, 0.0)
    g.update(None, 0.5)
    assert g.allowed(0.5) and not g.allowed(1.6)
    lenient = AttentionGate(grace_s=1.0, require_face=False)
    lenient.update(None, 0.0)
    lenient.update(None, 5.0)
    assert lenient.allowed(5.0)                                          # only a clearly turned face blocks


# ---------------------------------------------------------------- the thread wrapper (with a fake detector, no camera)
class FakeDetector:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        return None if self.rows is None else np.stack(self.rows)


def test_attention_uses_the_detector_and_rate_limits_it():
    det = FakeDetector([face(10)])
    a = Attention(det, AttentionGate(), check_every_s=0.2, threaded=False)
    frame = np.zeros((480, 640, 3), np.uint8)
    a.submit(frame, 0.0)
    a.submit(frame, 0.05)                                                # too soon: skipped
    a.submit(frame, 0.3)
    assert det.calls == 2 and a.allowed(0.3) and "facing the screen" in a.describe(0.3)


def test_attention_reports_looking_away_and_no_face():
    frame = np.zeros((480, 640, 3), np.uint8)
    away = Attention(FakeDetector([face(70)]), AttentionGate(grace_s=0.0), check_every_s=0.0, threaded=False)
    away.submit(frame, 1.0)
    assert not away.allowed(1.5) and "LOOKING AWAY" in away.describe(1.5)
    nobody = Attention(FakeDetector(None), AttentionGate(grace_s=0.0), check_every_s=0.0, threaded=False)
    nobody.submit(frame, 0.5)
    assert not nobody.allowed(0.6) and "looking for a face" in nobody.describe(0.6)     # nobody has been seen yet
    nobody.gate.update(5.0, 1.0)                                                         # now you sit down...
    nobody.submit(frame, 1.2)                                                            # ...and then your face leaves the picture
    assert not nobody.allowed(2.5) and "no face" in nobody.describe(2.5)


def test_a_failing_detector_does_not_crash_the_loop():
    class Broken:
        def detect(self, frame):
            raise RuntimeError("boom")

    a = Attention(Broken(), AttentionGate(), check_every_s=0.0, threaded=False)
    a.submit(np.zeros((10, 10, 3), np.uint8), 0.0)                       # no exception
    assert not a.allowed(0.0)


def test_the_threaded_worker_never_blocks_the_caller():
    import time

    class Slow(FakeDetector):
        def detect(self, frame):
            time.sleep(0.3)
            return super().detect(frame)

    a = Attention(Slow([face(5)]), AttentionGate(), check_every_s=0.0, threaded=True)
    t0 = time.time()
    for i in range(20):
        a.submit(np.zeros((10, 10, 3), np.uint8), i * 0.01)
    assert time.time() - t0 < 0.2                                        # submit returns at once
    time.sleep(0.6)
    assert a.allowed(0.2)
    a.close()


def test_it_is_off_by_default_and_the_defaults_are_sensible():
    assert DEFAULTS["enabled"] is False
    assert 20 <= DEFAULTS["max_turn_deg"] <= 50 and DEFAULTS["grace_s"] >= 0.5
