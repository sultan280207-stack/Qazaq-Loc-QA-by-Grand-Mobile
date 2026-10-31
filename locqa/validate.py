"""Offline approximation of what `flutter gen-l10n` rejects.

Run the real `flutter gen-l10n` in CI (see .github/workflows/locqa.yml); this
validator catches the same classes of errors without the Flutter SDK:
invalid JSON, messages that are not valid ICU, placeholders that the template
message does not have, plural arguments without `other`, broken metadata.
"""
from __future__ import annotations

from . import icu
from .arb import ArbFile


def validate(template: ArbFile, arb: ArbFile) -> list[str]:
    errors = []
    tmpl = template.messages()
    for key in arb.keys():
        msg = arb.value(key)
        try:
            nodes = icu.parse(msg)
        except icu.IcuError as e:
            errors.append(f"{key}: ICU syntax error: {e}")
            continue
        args = icu.arguments(nodes)
        for a in args:
            if a.is_complex and "other" not in a.options:
                errors.append(f"{key}: {a.kind} '{a.name}' has no 'other' case")
        if key in tmpl:
            try:
                t_names = {a.name for a in icu.arguments(icu.parse(tmpl[key]))}
            except icu.IcuError:
                t_names = set()
            meta = template.metadata(key) or {}
            t_names |= set((meta.get("placeholders") or {}).keys())
            extra = {a.name for a in args} - t_names
            if extra:
                errors.append(f"{key}: placeholders {sorted(extra)} are not in the template message")
    for e in arb.entries:
        if e.key.startswith("@") and not e.key.startswith("@@"):
            if not isinstance(e.value, dict):
                errors.append(f"{e.key}: metadata must be an object")
            elif e.key[1:] not in arb:
                errors.append(f"{e.key}: metadata without message")
    seen = {}
    for e in arb.entries:
        if e.key.startswith("@") and not e.key.startswith("@@"):
            if e.key in seen:
                errors.append(f"{e.key}: duplicated metadata (lines {seen[e.key]} and {e.line}) - the first one is lost")
            seen[e.key] = e.line
    return errors
