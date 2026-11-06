from types import SimpleNamespace as P

from hexra.gate import AirGate


def hand(cy=0.4, x=0.5):
    pts = [P(x=x, y=cy, z=0.0) for _ in range(21)]
    return pts


def feed(g, lm, pose, t0, secs, fps=30):
    out = None
    for i in range(int(secs * fps)):
        out = g.update(lm, pose, t0 + i / fps)
    return out


def test_starts_asleep_and_ignores_gestures():
    g = AirGate()
    assert feed(g, hand(), "click", 0, 3) is False and not g.awake


def test_wakes_after_holding_open_palm_in_air():
    g = AirGate()
    assert feed(g, hand(), "palm", 0, 0.5) is False        # not long enough
    assert feed(g, hand(), "palm", 1, 1.5) is True and g.awake


def test_resting_low_hand_never_wakes():
    g = AirGate()
    assert feed(g, hand(cy=0.9), "palm", 0, 5) is False and not g.awake


def test_hand_cut_off_by_frame_edge_is_not_in_air():
    g = AirGate()
    assert not g.in_air(hand(x=0.995))


def test_brief_pose_wobble_resets_wake_timer():
    g = AirGate()
    feed(g, hand(), "palm", 0, 0.7)
    feed(g, hand(), "fist", 0.7, 0.1)
    assert feed(g, hand(), "palm", 0.8, 0.5) is False


def test_lowering_hand_ignores_then_sleeps():
    g = AirGate()
    feed(g, hand(), "palm", 0, 1.5)
    assert g.awake
    assert feed(g, hand(cy=0.9), "palm", 1.5, 0.5) is False and g.awake   # ignored at once, still awake
    feed(g, hand(cy=0.9), "palm", 2.0, 1.5)
    assert not g.awake
    assert feed(g, hand(), "click", 4.5, 0.5) is False                    # asleep: needs the wake hold again


def test_disabled_gate_passes_everything():
    g = AirGate(enabled=False)
    assert g.update(hand(cy=0.95), "click", 0.0) is True
    assert g.update(None, None, 0.1) is False


def test_reaching_low_and_to_the_edge_while_dragging_does_not_drop():
    g = AirGate()
    feed(g, hand(), "palm", 0, 1.5)
    low = hand(cy=0.9, x=0.99)                                   # centre low and right at the frame edge
    assert g.update(low, "click", 2.0, holding=False) is False   # normally ignored
    assert g.update(low, "click", 2.1, holding=True) is True     # but fine while holding a drag


def test_negative_edge_margin_accepts_a_hand_partly_out_of_the_picture():
    strict, lenient = AirGate(edge_margin=0.02), AirGate(edge_margin=-0.15)
    cut_off = hand(cy=0.4, x=1.05)                    # the hand's points are 5% beyond the right edge
    assert not strict.in_air(cut_off)
    assert lenient.in_air(cut_off)
    assert not lenient.in_air(hand(cy=0.4, x=1.3))   # but not when it is mostly outside
    assert not lenient.in_air(hand(cy=0.97, x=0.5))  # and the bottom line still applies


def test_the_line_uses_the_same_point_as_the_ball_and_sits_low_by_default():
    from hexra.app import load_config

    cfg = load_config("config.yaml")
    g = AirGate(**cfg.air)
    assert cfg.air["max_center_y"] == 0.95
    assert g.in_air(hand(cy=0.85, x=0.5))          # a hand well down the picture now works
    assert not g.in_air(hand(cy=0.98, x=0.5))      # only the very bottom is ignored
