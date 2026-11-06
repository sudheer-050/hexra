import pytest

from hexra.app import load_config
from hexra.controller import FEEL


def write(tmp_path, text, bom=False):
    p = tmp_path / "config.yaml"
    text = "screen: {width: 1920, height: 1080}\n" + text  # fixed size, so tests never need tkinter
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    return str(p)


def test_shipped_config_loads():
    cfg = load_config("config.yaml")
    assert (cfg.min_cutoff, cfg.beta, cfg.deadzone_px) == FEEL["responsive"]
    assert cfg.cursor_mode == "relative" and cfg.camera == {"width": 640, "height": 480}
    assert cfg.actions["fist"] == "move_window"


def test_file_with_byte_order_mark_loads(tmp_path):
    cfg = load_config(write(tmp_path, "# comment\nfeel: responsive\n", bom=True))
    assert (cfg.min_cutoff, cfg.beta, cfg.deadzone_px) == FEEL["responsive"]


def test_explicit_values_override_the_preset(tmp_path):
    cfg = load_config(write(tmp_path, "feel: smooth\nbeta: 99\n"))
    assert cfg.min_cutoff == FEEL["smooth"][0] and cfg.beta == 99.0


def test_unknown_feel_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        load_config(write(tmp_path, "feel: turbo\n"))
