"""Write `intl_<lang>_fixed.arb`: apply suggestions, keep layout, flag review status.

Every changed or added message gets ARB metadata (custom attributes use the
`x-` prefix allowed by the ARB spec and ignored by `flutter gen-l10n`):

    "@key": {"x-reviewed_by_human": false, "x-locqa-issues": "orthography",
             "x-locqa-original": "<previous value>"}

For a duplicated key every occurrence gets the new text (Flutter reads the last one),
and the metadata is written once, after the last occurrence.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .arb import ArbFile
from .issues import Issue

_VAL = re.compile(r'^(\s*"((?:[^"\\]|\\.)*)"\s*:\s*)"((?:[^"\\]|\\.)*)"(\s*,?\s*)$')


def _enc(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)[1:-1]


def plan_changes(issues: list[Issue], source: ArbFile, target: ArbFile) -> dict[str, dict]:
    """key -> {value, issues, reviewed, added} using the best suggestion per key."""
    rank = {"review": 0, "auto+review": 1, "auto": 2}
    best: dict[str, Issue] = {}
    types: dict[str, set] = {}
    reviewed: dict[str, list[bool]] = {}
    for i in issues:
        if not i.suggestion:
            continue
        types.setdefault(i.key, set()).add(i.issue_type)
        reviewed.setdefault(i.key, []).append(i.reviewed_by_human)
        cur = best.get(i.key)
        if cur is None or (rank.get(i.origin, 3), -i.confidence) < (rank.get(cur.origin, 3), -cur.confidence):
            best[i.key] = i
    plan = {}
    for k, i in best.items():
        old = target.value(k)
        if old is not None and i.suggestion == old:
            continue
        plan[k] = {"value": i.suggestion, "issues": sorted(types[k]), "reviewed": all(reviewed[k]),
                   "added": old is None, "original": old}
    return plan


def write_fixed(source: ArbFile, target: ArbFile, plan: dict[str, dict], out: str | Path) -> dict:
    lines = target.text.split("\n")
    edits, inserts = {}, []
    src_keys = source.keys()
    for key, ch in plan.items():
        if not ch["added"]:
            occ = [e for e in target.occurrences(key) if isinstance(e.value, str)]
            # Flutter reads the last occurrence; earlier duplicates get the same text so the
            # file stays consistent, metadata goes after the last one only
            for e in occ:
                edits[e.line - 1] = (key, ch, e is occ[-1])
        else:
            inserts.append((key, ch))
    meta_after: dict[int, list[str]] = {}
    for idx, (key, ch, last) in edits.items():
        m = _VAL.match(lines[idx])
        if not m or json.loads('"' + m.group(2) + '"') != key:
            raise ValueError(f"line {idx + 1}: cannot edit value of {key!r} in place")
        lines[idx] = m.group(1) + '"' + _enc(ch["value"]) + '"' + m.group(4)
        if not last:
            continue
        indent = re.match(r"^(\s*)", lines[idx]).group(1)
        if target.metadata(key) is None:
            meta_after.setdefault(idx, []).append(indent + _meta_line(key, ch))
        else:
            _merge_existing_meta(lines, target, key, ch)
    # new keys: after the nearest preceding source key that exists in target
    for key, ch in inserts:
        pos = src_keys.index(key) if key in src_keys else len(src_keys)
        anchor, after = None, True
        for j in range(pos - 1, -1, -1):
            e = target.entry(src_keys[j])
            if e and e.line:
                anchor = e.line - 1; break
        if anchor is None:
            for j in range(pos + 1, len(src_keys)):
                e = target.entry(src_keys[j])
                if e and e.line:
                    anchor, after = e.line - 1, False; break
        if anchor is None:
            anchor = max(i for i, l in enumerate(lines) if l.strip()) - 1
        indent = re.match(r"^(\s*)", lines[anchor]).group(1) or "  "
        block = [f'{indent}"{key}": "{_enc(ch["value"])}",', indent + _meta_line(key, ch)]
        if after:
            meta_after.setdefault(anchor, []).extend(block)
        else:
            meta_after.setdefault(anchor - 1, []).extend(block)
    out_lines: list[str] = []
    for i, l in enumerate(lines):
        out_lines.append(l)
        extra = meta_after.get(i)
        if extra:
            # the last non-blank line before the inserted block needs a comma
            j = len(out_lines) - 1
            while j >= 0 and not out_lines[j].strip():
                j -= 1
            if j >= 0 and not out_lines[j].rstrip().endswith((",", "{")):
                out_lines[j] = out_lines[j].rstrip() + ","
            out_lines.extend(extra)
    # no trailing comma right before a closing brace
    for j in range(len(out_lines)):
        if out_lines[j].strip().startswith("}"):
            k = j - 1
            while k >= 0 and not out_lines[k].strip():
                k -= 1
            if k >= 0 and out_lines[k].rstrip().endswith(","):
                out_lines[k] = out_lines[k].rstrip()[:-1]
    text = "\n".join(out_lines)
    json.loads(text)  # must stay valid JSON
    Path(out).write_text(text, encoding="utf-8")
    return {"changed": sum(1 for _, _, last in edits.values() if last), "added": len(inserts),
            "reviewed": sum(1 for c in plan.values() if c["reviewed"]),
            "unreviewed": sum(1 for c in plan.values() if not c["reviewed"])}


def _meta_line(key: str, ch: dict) -> str:
    meta = {"x-reviewed_by_human": bool(ch["reviewed"]), "x-locqa-issues": ",".join(ch["issues"])}
    if ch.get("original") is not None:
        meta["x-locqa-original"] = ch["original"]
    return f'"@{key}": ' + json.dumps(meta, ensure_ascii=False) + ","


def _merge_existing_meta(lines, target: ArbFile, key: str, ch: dict) -> None:
    occ = target.occurrences("@" + key)[-1]
    i = occ.line - 1
    flag = f'"x-reviewed_by_human": {str(bool(ch["reviewed"])).lower()}, "x-locqa-issues": "{",".join(ch["issues"])}"'
    if lines[i].rstrip().endswith("{"):
        indent = re.match(r"^(\s*)", lines[i]).group(1) + "  "
        lines[i] = lines[i] + "\n" + indent + flag + ","
    else:
        lines[i] = lines[i].replace("{", "{ " + flag + ",", 1).replace(",}", "}").replace(", }", " }")
