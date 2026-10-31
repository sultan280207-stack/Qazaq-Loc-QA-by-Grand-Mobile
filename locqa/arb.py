"""ARB file loading that keeps everything a strict JSON parser throws away.

ARB files in the wild repeat keys (most often "@@comment" used as a section
marker), so a plain json.load() keeps only the last value.  ArbFile keeps every
occurrence in file order together with its line number and the section name
taken from the nearest preceding "@@comment".  Flutter (Dart's jsonDecode)
uses the *last* occurrence of a duplicated key, so `value(key)` does the same.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_KEY_LINE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*:')


@dataclass
class Entry:
    key: str
    value: object
    line: int | None
    section: str | None
    index: int  # position among all top-level pairs

    @property
    def is_message(self) -> bool:
        return not self.key.startswith("@") and isinstance(self.value, str)


@dataclass
class ArbFile:
    path: Path
    text: str
    entries: list[Entry]
    locale: str | None = None
    _by_key: dict[str, list[Entry]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for e in self.entries:
            self._by_key.setdefault(e.key, []).append(e)

    # ---- access -------------------------------------------------------
    def keys(self) -> list[str]:
        """Message keys (no @-metadata) in first-occurrence order."""
        seen, out = set(), []
        for e in self.entries:
            if e.is_message and e.key not in seen:
                seen.add(e.key)
                out.append(e.key)
        return out

    def __contains__(self, key: str) -> bool:
        return key in self._by_key

    def occurrences(self, key: str) -> list[Entry]:
        return self._by_key.get(key, [])

    def entry(self, key: str) -> Entry | None:
        occ = [e for e in self._by_key.get(key, []) if e.is_message]
        return occ[-1] if occ else None

    def value(self, key: str) -> str | None:
        e = self.entry(key)
        return e.value if e else None

    def metadata(self, key: str) -> dict | None:
        occ = self._by_key.get("@" + key)
        if occ and isinstance(occ[-1].value, dict):
            return occ[-1].value
        return None

    def messages(self) -> dict[str, str]:
        return {k: self.value(k) for k in self.keys()}

    def duplicates(self) -> dict[str, list[Entry]]:
        return {k: v for k, v in self._by_key.items()
                if len(v) > 1 and not k.startswith("@")}


def load_arb(path: str | Path) -> ArbFile:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    pairs = json.loads(text, object_pairs_hook=lambda p: p)
    if not isinstance(pairs, list):
        raise ValueError(f"{path}: top level of an ARB file must be an object")
    # map top-level keys to line numbers (only lines that start a top-level key)
    key_lines: dict[str, list[int]] = {}
    depth = 0
    for no, line in enumerate(text.split("\n"), 1):
        if depth == 1:
            m = _KEY_LINE.match(line)
            if m:
                key_lines.setdefault(json.loads('"' + m.group(1) + '"'), []).append(no)
        depth += _brace_delta(line)
    seen: dict[str, int] = {}
    entries, section, locale = [], None, None
    for i, (k, v) in enumerate(pairs):
        n = seen.get(k, 0)
        seen[k] = n + 1
        lines = key_lines.get(k, [])
        ln = lines[n] if n < len(lines) else None
        if k == "@@comment" and isinstance(v, str):
            section = v
        if k == "@@locale" and isinstance(v, str):
            locale = v
        if isinstance(v, list):  # nested objects arrive as pair lists
            v = _to_dict(v)
        entries.append(Entry(k, v, ln, section, i))
    if locale is None:
        m = re.search(r"_([a-z]{2,3}(?:_[A-Za-z]+)?)\.arb$", path.name)
        locale = m.group(1) if m else None
    return ArbFile(path, text, entries, locale)


def _to_dict(pairs):
    out = {}
    for k, v in pairs:
        if isinstance(v, list) and (not v or isinstance(v[0], tuple)):
            v = _to_dict(v)
        out[k] = v
    return out


def _brace_delta(line: str) -> int:
    """Net change of object depth on a line, ignoring braces inside strings."""
    d, in_str, esc = 0, False, False
    for ch in line:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            d += 1
        elif ch == "}":
            d -= 1
    return d
