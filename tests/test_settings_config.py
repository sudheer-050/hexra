"""The settings catalogue and the comment-preserving config.yaml writer."""
from pathlib import Path

import pytest
import yaml

from hexra import config_io, settings_schema as schema

ROOT = Path(__file__).resolve().parent.parent
REAL = (ROOT / "config.yaml").read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------- the catalogue
def test_every_setting_is_listed_once_with_a_valid_default():
    ids = [s["id"] for s in schema.flatten()]
    assert len(ids) == len(set(ids))
    for s in schema.flatten():
        if s["default"] is not None or s["type"] == "enum":
            assert schema.validate_value(s, s["default"]) == s["default"] or s["type"] == "number", s["id"]


def test_the_catalogue_covers_every_key_in_the_shipped_config():
    ids = {s["id"] for s in schema.flatten()}
    data = yaml.safe_load(REAL)
    missing = []
    for key, val in data.items():
        if isinstance(val, dict):
            for sub in val:
                sid = f"{key}.{sub}"
                if sid in ("camera.width", "camera.height", "face_lock.admin_file"):
                    continue
                if key == "actions":
                    if f"actions.{sub}" not in ids:
                        missing.append(sid)
                elif sid not in ids:
                    missing.append(sid)
        elif key not in ids:
            missing.append(key)
    assert not missing, f"settings in config.yaml with no entry in the settings catalogue: {missing}"
    assert "camera.resolution" in ids


def test_catalogue_defaults_match_the_shipped_config():
    shipped = config_io.values_from_text(REAL)
    differ = {k: (shipped[k], v) for k, v in schema.defaults().items() if shipped[k] != v and k != "face_lock.enabled"}
    assert not differ, differ                       # (face_lock.enabled is on in the developer's config but off in the installer)


def test_every_setting_explains_itself_and_its_latency():
    for s in schema.flatten():
        assert s["label"] and len(s["desc"]) > 15, s["id"]
        imp = s["impact"]
        assert imp["kind"] in ("none", "frames", "seconds", "options", "note", "action"), s["id"]
        if s["type"] == "enum":
            assert all("ms" in o and o["tone"] in ("good", "neutral", "warn") for o in s["options"]), s["id"]
        if imp["kind"] in ("note", "frames", "seconds"):
            assert imp["text"] and imp.get("basis") in ("measured", "simulation", "calculated", "estimate"), s["id"]


def test_every_pose_can_be_given_any_action():
    assert [p[0] for p in schema.POSES] == [s["pose"] for s in schema.flatten() if s["type"] == "action"]


# ---------------------------------------------------------------- validation
def test_numbers_are_checked_clamped_to_the_step_and_keep_their_type():
    hold = schema.by_id()["hold_frames"]
    assert schema.validate_value(hold, 4) == 4 and isinstance(schema.validate_value(hold, 4.0), int)
    with pytest.raises(schema.SettingError):
        schema.validate_value(hold, 99)
    with pytest.raises(schema.SettingError):
        schema.validate_value(hold, "3")
    with pytest.raises(schema.SettingError):
        schema.validate_value(hold, True)
    assert schema.validate_value(schema.by_id()["air.wake_seconds"], 1.04) == 1.0     # rounded to its 0.1 step
    assert schema.validate_value(schema.by_id()["rel_softness"], 0.00031) == 0.0003


def test_optional_overrides_may_be_empty_but_normal_numbers_may_not():
    assert schema.validate_value(schema.by_id()["min_cutoff"], None) is None
    with pytest.raises(schema.SettingError):
        schema.validate_value(schema.by_id()["hold_frames"], None)


def test_choices_booleans_actions_and_the_active_box_are_checked():
    with pytest.raises(schema.SettingError):
        schema.validate_value(schema.by_id()["feel"], "turbo")
    with pytest.raises(schema.SettingError):
        schema.validate_value(schema.by_id()["snap_edges"], 1)
    with pytest.raises(schema.SettingError):
        schema.validate_value(schema.by_id()["actions.fist"], "format_disk")
    assert schema.validate_value(schema.by_id()["actions.fist"], "none") == "none"
    box = schema.by_id()["region"]
    assert schema.validate_value(box, [0.1, 0.1, 0.9, 0.8]) == [0.1, 0.1, 0.9, 0.8]
    for bad in ([0.5, 0.1, 0.4, 0.8], [0, 0, 1], [0.1, 0.1, 0.15, 0.8], [-0.1, 0, 1, 1], "x"):
        with pytest.raises(schema.SettingError):
            schema.validate_value(box, bad)


def test_unknown_settings_and_inconsistent_pairs_are_refused():
    with pytest.raises(schema.SettingError):
        schema.validate_all({"format_c": True})
    with pytest.raises(schema.SettingError):
        schema.validate_all({"rel_v_low": 0.9, "rel_v_high": 0.5})
    with pytest.raises(schema.SettingError):
        schema.validate_all({"rel_gain_min": 3.0, "rel_gain_max": 1.0})


# ---------------------------------------------------------------- the writer
def changed_lines(a: str, b: str):
    return [(x, y) for x, y in zip(a.splitlines(), b.splitlines()) if x != y]


def test_changing_values_keeps_every_comment_and_only_touches_those_lines():
    new = config_io.apply_changes(REAL, [(("feel",), "balanced"), (("hold_frames",), 4), (("air", "wake_seconds"), 1.5), (("actions", "fist"), "none")])
    assert sum(1 for l in new.splitlines() if l.strip().startswith("#")) == sum(1 for l in REAL.splitlines() if l.strip().startswith("#"))
    diff = changed_lines(REAL, new)
    assert len(diff) == 4 and len(new.splitlines()) == len(REAL.splitlines())
    data = yaml.safe_load(new)
    assert data["feel"] == "balanced" and data["hold_frames"] == 4 and data["air"]["wake_seconds"] == 1.5 and data["actions"]["fist"] == "none"
    assert "# frames a click/right-click/scroll must persist" in [l for l in new.splitlines() if l.startswith("hold_frames")][0]   # its comment stayed


def test_a_missing_key_is_added_to_its_block_and_a_missing_block_is_appended():
    text = "feel: responsive\nair:\n  enabled: true\n  wake_seconds: 1.0  # hold this long\n\n# the end\n"
    new = config_io.apply_changes(text, [(("air", "sleep_seconds"), 2.0), (("attention", "enabled"), True), (("min_cutoff",), 1.2)])
    data = yaml.safe_load(new)
    assert data["air"] == {"enabled": True, "wake_seconds": 1.0, "sleep_seconds": 2.0}
    assert data["attention"] == {"enabled": True} and data["min_cutoff"] == 1.2
    assert "# hold this long" in new and "# the end" in new


def test_clearing_an_optional_override_removes_the_line():
    text = "feel: balanced\nmin_cutoff: 1.0   # custom\nbeta: 25\n"
    new = config_io.apply_changes(text, [(("min_cutoff",), config_io.REMOVE)])
    assert yaml.safe_load(new) == {"feel": "balanced", "beta": 25} and "custom" not in new


def test_line_endings_are_kept():
    new = config_io.apply_changes("feel: responsive\r\nhold_frames: 3\r\n", [(("hold_frames",), 5)])
    assert new == "feel: responsive\r\nhold_frames: 5\r\n"


def test_numbers_never_come_out_in_a_form_yaml_reads_as_text():
    assert config_io.fmt(0.00003) == "0.00003" and config_io.fmt(3.0) == "3.0" and config_io.fmt(True) == "true"
    assert config_io.fmt([0.2, 0.15, 0.8, 0.7]) == "[0.2, 0.15, 0.8, 0.7]" and config_io.fmt(None) == "null" and config_io.fmt("relative") == "relative"
    assert yaml.safe_load("a: " + config_io.fmt(0.00003))["a"] == 0.00003
    assert config_io.fmt("yes") == '"yes"'


def test_a_compact_block_the_app_cannot_edit_safely_is_refused():
    with pytest.raises(config_io.ConfigError):
        config_io.apply_changes("screen: { span: all }\n", [(("screen", "span"), "primary")])


def test_saving_the_real_config_round_trips_every_setting(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(REAL, encoding="utf-8")
    before = config_io.read_values(f)
    # change EVERY setting to a different valid value, save, read back
    changes = {}
    for s in schema.flatten():
        sid, cur = s["id"], before[s["id"]]
        if s["type"] == "bool":
            changes[sid] = not cur
        elif s["type"] == "number":
            changes[sid] = s["min"] if cur != s["min"] else s["max"]
        elif s["type"] in ("enum",):
            changes[sid] = next(o["value"] for o in s["options"] if o["value"] != cur)
        elif s["type"] == "action":
            changes[sid] = "none" if cur != "none" else "move"
        elif s["type"] == "region":
            changes[sid] = [0.1, 0.1, 0.9, 0.9]
        elif s["type"] == "cameras":
            changes[sid] = [0, 1]
    changes["rel_v_low"], changes["rel_v_high"] = 0.05, 0.9
    changes["rel_gain_min"], changes["rel_gain_max"] = 1.0, 4.0
    config_io.save_values(f, changes)
    after = config_io.read_values(f)
    clean = schema.validate_all(changes)
    for sid, want in clean.items():
        assert after[sid] == want, (sid, after[sid], want)
    assert (tmp_path / "config.yaml.bak").read_text(encoding="utf-8") == REAL                  # the previous file is kept
    assert sum(1 for l in f.read_text(encoding="utf-8").splitlines() if l.strip().startswith("#")) >= sum(1 for l in REAL.splitlines() if l.strip().startswith("#"))
    # the app itself must still be able to load what was written
    from hexra.app import load_config
    cfg = load_config(str(f))
    assert cfg.hold_frames == clean["hold_frames"] and cfg.actions["fist"] == clean["actions.fist"] and cfg.attention["enabled"] == clean["attention.enabled"]


def test_nothing_is_written_when_the_input_is_invalid(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(REAL, encoding="utf-8")
    with pytest.raises(schema.SettingError):
        config_io.save_values(f, {"feel": "responsive", "hold_frames": 500})
    assert f.read_text(encoding="utf-8") == REAL and not (tmp_path / "config.yaml.bak").exists()


def test_a_missing_file_is_created_from_defaults_and_a_bom_is_accepted(tmp_path):
    f = tmp_path / "new.yaml"
    config_io.save_values(f, {"feel": "smooth", "attention.enabled": True})
    assert config_io.read_values(f)["feel"] == "smooth" and config_io.read_values(f)["attention.enabled"] is True
    g = tmp_path / "bom.yaml"
    g.write_bytes(b"\xef\xbb\xbffeel: balanced\n")
    assert config_io.read_values(g)["feel"] == "balanced"


def test_a_value_the_app_does_not_allow_is_shown_as_the_default_not_a_crash():
    assert config_io.values_from_text("feel: warp\nhold_frames: 400\n")["feel"] == "responsive"


def test_cameras_choose_one_or_two_different_ones():
    cam = schema.by_id()["camera.use"]
    assert schema.validate_value(cam, [0]) == [0] and schema.validate_value(cam, [1, 0]) == [0, 1]
    for bad in ([], [0, 1, 2], [1, 1], [-1], [9], "0", [True], None):
        with pytest.raises(schema.SettingError):
            schema.validate_value(cam, bad)


def test_two_cameras_switch_the_face_direction_gate_off():
    clean = schema.validate_all({"camera.use": [0, 1], "attention.enabled": True})
    assert clean["attention.enabled"] is False
    assert schema.validate_all({"camera.use": [0], "attention.enabled": True})["attention.enabled"] is True


def test_the_camera_choice_is_written_as_a_list_and_read_back(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(REAL, encoding="utf-8")
    config_io.save_values(f, {"camera.use": [0, 1]})
    assert config_io.read_values(f)["camera.use"] == [0, 1]
    assert yaml.safe_load(f.read_text(encoding="utf-8"))["camera"]["use"] == [0, 1]
    assert yaml.safe_load(f.read_text(encoding="utf-8"))["camera"]["width"] == 640          # the neighbours are untouched
