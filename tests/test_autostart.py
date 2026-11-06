"""Start with Windows: a single value in a Run-style registry key. Tests use their own key, never the real Run key."""
import sys
from pathlib import Path

import pytest

from hexra import autostart

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
KEY = r"Software\HexraTest\Run"


@pytest.fixture()
def exe(tmp_path):
    f = tmp_path / "Hexra.exe"
    f.write_bytes(b"")
    yield f
    import winreg
    for sub in (KEY, r"Software\HexraTest"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            pass


def test_switching_it_on_and_off_writes_and_removes_one_value(exe):
    assert not autostart.is_enabled(KEY)
    autostart.set_enabled(True, exe, KEY)
    assert autostart.is_enabled(KEY)
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        val, _ = winreg.QueryValueEx(k, "Hexra")
    assert val == f'"{exe}" --background'                       # quoted path (spaces are safe) and starts hidden in the tray
    autostart.set_enabled(False, exe, KEY)
    assert not autostart.is_enabled(KEY)
    autostart.set_enabled(False, exe, KEY)                      # turning off twice is fine


def test_it_refuses_to_register_a_program_that_is_not_there(tmp_path):
    with pytest.raises(RuntimeError):
        autostart.set_enabled(True, tmp_path / "missing.exe", KEY)
    assert not autostart.is_enabled(KEY)


def test_the_command_is_quoted_and_hidden():
    assert autostart.command(Path(r"C:\Program Files\Hexra\Hexra.exe")) == r'"C:\Program Files\Hexra\Hexra.exe" --background'
