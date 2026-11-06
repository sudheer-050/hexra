"""Read and write config.yaml for the settings app, keeping everything the user wrote.

PyInstaller-style "dump the whole file" would throw away every comment, so changes are made as careful line edits: a value is
replaced in place (its trailing comment stays), a missing key is added to its block, a missing block is appended, and a cleared
optional override is removed. After every edit the new text is parsed again and compared with what was asked for; if anything
differs, nothing is written. The previous file is kept as config.yaml.bak.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal
from pathlib import Path

from . import settings_schema as schema

BLOCKS = {"air", "attention", "face_lock", "camera", "screen", "actions"}
REMOVE = object()


class ConfigError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------------------------ reading
def _load(text: str) -> dict:
    import yaml

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ConfigError("config.yaml is not a settings file (it must be key: value pairs)")
    return data


def read_text(path) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8-sig") if p.exists() else ""


def values_from_text(text: str) -> dict:
    """{setting id: value} for every setting, using the file's value where there is one and the default otherwise."""
    data = _load(text)
    out = {}
    for s in schema.flatten():
        sid = s["id"]
        if sid == "camera.resolution":
            cam = data.get("camera") or {}
            w, h = cam.get("width", 640), cam.get("height", 480)
            out[sid] = f"{int(w)}x{int(h)}"
        elif "." in sid:
            block, key = sid.split(".", 1)
            sect = data.get(block) or {}
            out[sid] = sect.get(key, s["default"]) if isinstance(sect, dict) else s["default"]
        else:
            out[sid] = data.get(sid, s["default"])
    for s in schema.flatten():                                       # a value the file holds but the app does not allow is shown as the default
        try:
            out[s["id"]] = schema.validate_value(s, out[s["id"]])
        except schema.SettingError:
            out[s["id"]] = s["default"]
    return out


def read_values(path) -> dict:
    return values_from_text(read_text(path))


# ------------------------------------------------------------------------------------------------------------------ writing
def to_paths(sid: str, value):
    """[(yaml path tuple, value)] for one setting id."""
    if sid == "camera.resolution":
        w, h = (int(x) for x in str(value).split("x"))
        return [(("camera", "width"), w), (("camera", "height"), h)]
    if value is None and schema.by_id()[sid]["default"] is None and schema.by_id()[sid]["type"] == "number":
        return [((sid,), REMOVE)]                                    # an optional override that was cleared: take the key out
    path = tuple(sid.split(".", 1)) if sid.split(".", 1)[0] in BLOCKS else (sid,)
    return [(path, value)]


def fmt(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        s = repr(value)
        if "e" in s or "E" in s:
            s = format(Decimal(s), "f")
        return s
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(fmt(v) for v in value) + "]"
    s = str(value)
    return s if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", s) and s.lower() not in ("true", "false", "null", "yes", "no", "on", "off") else '"' + s.replace('"', '\\"') + '"'


_SCALAR_TAIL = r"(?P<v>[^#\n]*?)(?P<c>[ \t]+#.*)?$"


def _replace_in_line(line: str, key: str, value) -> str:
    m = re.match(rf"^(?P<k>\s*{re.escape(key)}:[ \t]*){_SCALAR_TAIL}", line)
    if not m:
        return line
    return f"{m.group('k')}{fmt(value)}{m.group('c') or ''}"


def _block_range(lines, name):
    """(header index, index just after the block's last line), or None."""
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(name)}:[ \t]*(#.*)?$", line):
            j = i + 1
            while j < len(lines) and (lines[j].strip() == "" or lines[j].lstrip().startswith("#") or lines[j][:1] in (" ", "\t")):
                j += 1
            return i, j
        if re.match(rf"^{re.escape(name)}:[ \t]*[{{\[]", line):
            raise ConfigError(f"'{name}' is written in a compact form that the settings app cannot edit safely; edit config.yaml by hand")
    return None


def apply_changes(text: str, changes) -> str:
    """Apply [(path tuple, value or REMOVE)] to the file text, preserving comments and layout."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    for path, value in changes:
        if len(path) == 1:
            key = path[0]
            idx = next((i for i, l in enumerate(lines) if re.match(rf"^{re.escape(key)}:", l)), None)
            if idx is not None:
                if value is REMOVE:
                    del lines[idx]
                else:
                    lines[idx] = _replace_in_line(lines[idx], key, value)
            elif value is not REMOVE:
                while lines and lines[-1].strip() == "":
                    lines.pop()
                lines.append(f"{key}: {fmt(value)}")
            continue
        block, key = path
        rng = _block_range(lines, block)
        if rng is None:
            if value is REMOVE:
                continue
            while lines and lines[-1].strip() == "":
                lines.pop()
            lines += ["", f"{block}:", f"  {key}: {fmt(value)}"]
            continue
        start, end = rng
        idx = next((i for i in range(start + 1, end) if re.match(rf"^\s+{re.escape(key)}:", lines[i])), None)
        if idx is not None:
            if value is REMOVE:
                del lines[idx]
            else:
                lines[idx] = _replace_in_line(lines[idx], key, value)
        elif value is not REMOVE:
            last = max((i for i in range(start + 1, end) if lines[i].strip() and not lines[i].lstrip().startswith("#")), default=start)
            lines.insert(last + 1, f"  {key}: {fmt(value)}")
    return nl.join(lines) + nl


def _lookup(data, path):
    cur = data
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return REMOVE
        cur = cur[k]
    return cur


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def save_values(path, changes: dict) -> dict:
    """Validate and save {setting id: value}. Returns {"saved": [ids], "text": new text}. Writes nothing if anything is wrong."""
    clean = schema.validate_all(changes)
    old = read_text(path)
    pairs = []
    for sid, val in clean.items():
        pairs += to_paths(sid, val)
    new = apply_changes(old, pairs)
    parsed = _load(new)                                              # the result must still be a valid settings file...
    for p, v in pairs:                                               # ...that says exactly what was asked for
        got = _lookup(parsed, p)
        if v is REMOVE:
            if got is not REMOVE:
                raise ConfigError(f"could not remove {'.'.join(p)}")
        elif got is REMOVE or not _same(got, v):
            raise ConfigError(f"could not set {'.'.join(p)} safely (the file would read {got!r} instead of {v!r}); nothing was changed")
    p = Path(path)
    if p.exists() and new != old:
        (p.parent / (p.name + ".bak")).write_text(old, encoding="utf-8", newline="")
    tmp = p.parent / (p.name + ".tmp")
    tmp.write_text(new, encoding="utf-8", newline="")
    os.replace(tmp, p)
    return {"saved": list(clean), "text": new}
