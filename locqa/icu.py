"""A small ICU MessageFormat parser, close to what `flutter gen-l10n` accepts.

Supported: plain text, simple arguments `{name}`, typed arguments
`{name, number|date|time, style}`, and complex arguments
`{name, plural|select|selectordinal, ...}` with nested messages, `=N` exact
selectors and `offset:N`.  Apostrophes are treated as literal text, which is
gen-l10n's default (`use-escaping: false`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
COMPLEX = {"plural", "select", "selectordinal"}
SIMPLE_TYPES = {"number", "date", "time", "spellout", "ordinal", "duration"}
PLURAL_CATEGORIES = {"zero", "one", "two", "few", "many", "other"}

# CLDR cardinal plural categories (subset of locales likely to appear)
CLDR_CARDINAL = {
    "ru": {"one", "few", "many", "other"}, "uk": {"one", "few", "many", "other"},
    "be": {"one", "few", "many", "other"}, "pl": {"one", "few", "many", "other"},
    "kk": {"one", "other"}, "uz": {"one", "other"}, "en": {"one", "other"},
    "es": {"one", "many", "other"}, "pt": {"one", "many", "other"},
    "tr": {"one", "other"}, "ky": {"one", "other"}, "de": {"one", "other"},
    "fr": {"one", "many", "other"}, "ar": {"zero", "one", "two", "few", "many", "other"},
    "ja": {"other"}, "zh": {"other"}, "ko": {"other"},
}


class IcuError(ValueError):
    def __init__(self, msg: str, pos: int):
        super().__init__(f"{msg} (position {pos})")
        self.pos = pos


@dataclass
class Argument:
    name: str
    kind: str = "simple"          # simple | number | date | ... | plural | select | selectordinal
    options: dict = field(default_factory=dict)   # selector -> list[node]
    style: str | None = None

    @property
    def is_complex(self) -> bool:
        return self.kind in COMPLEX


def parse(message: str) -> list:
    """Parse a message into nodes: str for text, Argument for arguments."""
    p = _Parser(message)
    nodes = p.message(top=True)
    if p.i != len(message):
        raise IcuError("unexpected '}'", p.i)
    return nodes


def arguments(nodes) -> list[Argument]:
    """All arguments, recursively, in order of appearance."""
    out = []
    for n in nodes:
        if isinstance(n, Argument):
            out.append(n)
            for sub in n.options.values():
                out.extend(arguments(sub))
    return out


def placeholder_names(message: str) -> list[str] | None:
    """Argument names (with repeats) or None if the message is not valid ICU."""
    try:
        return [a.name for a in arguments(parse(message))]
    except IcuError:
        return None


class _Parser:
    def __init__(self, s: str):
        self.s, self.i = s, 0

    def message(self, top=False, in_plural=False):
        nodes, buf = [], []
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch == "{":
                if buf:
                    nodes.append("".join(buf)); buf = []
                nodes.append(self.argument())
            elif ch == "}":
                if top:
                    raise IcuError("unmatched '}'", self.i)
                break
            else:
                buf.append(ch); self.i += 1
        if buf:
            nodes.append("".join(buf))
        return nodes

    def ws(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def ident(self, what):
        self.ws()
        m = IDENT.match(self.s, self.i)
        if not m:
            raise IcuError(f"expected {what}", self.i)
        self.i = m.end()
        return m.group(0)

    def expect(self, ch):
        self.ws()
        if self.i >= len(self.s) or self.s[self.i] != ch:
            raise IcuError(f"expected '{ch}'", self.i)
        self.i += 1

    def argument(self):
        start = self.i
        self.i += 1  # '{'
        name = self.ident("placeholder name")
        self.ws()
        if self.i < len(self.s) and self.s[self.i] == "}":
            self.i += 1
            return Argument(name)
        self.expect(",")
        kind = self.ident("argument type")
        self.ws()
        if kind in COMPLEX:
            self.expect(",")
            arg = Argument(name, kind)
            self.ws()
            if self.s.startswith("offset:", self.i):
                self.i += len("offset:")
                m = re.compile(r"\s*\d+").match(self.s, self.i)
                if not m:
                    raise IcuError("bad offset", self.i)
                self.i = m.end()
            while True:
                self.ws()
                if self.i >= len(self.s):
                    raise IcuError(f"unclosed {kind} argument '{name}'", start)
                if self.s[self.i] == "}":
                    self.i += 1
                    break
                m = re.compile(r"=\d+|[A-Za-z_][A-Za-z0-9_]*").match(self.s, self.i)
                if not m:
                    raise IcuError(f"expected selector in '{name}'", self.i)
                sel = m.group(0); self.i = m.end()
                self.expect("{")
                body = self.message(in_plural=kind != "select")
                if self.i >= len(self.s):
                    raise IcuError(f"unclosed option '{sel}' of '{name}'", self.i)
                self.i += 1  # '}'
                if sel in arg.options:
                    raise IcuError(f"duplicate selector '{sel}' in '{name}'", self.i)
                arg.options[sel] = body
            if not arg.options:
                raise IcuError(f"{kind} '{name}' has no options", start)
            return arg
        # simple typed argument: {n, number} or {n, number, style}
        style = None
        if self.i < len(self.s) and self.s[self.i] == ",":
            self.i += 1
            j = self.s.find("}", self.i)
            if j < 0:
                raise IcuError("unclosed argument", start)
            style = self.s[self.i:j].strip(); self.i = j
        self.expect("}")
        return Argument(name, kind, style=style)
