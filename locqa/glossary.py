"""Glossary: CSV with required columns ru, kk, en, comment.

Optional columns make an entry checkable:
  ru_match   regex that finds the term in the source (default: stem of `ru`)
  kk_match   regex of accepted target renderings (default: stem of `kk`)
  kk_avoid   regex of renderings that are always wrong for this term
  strict     yes/no - if yes, a source hit without a kk_match hit is reported
  issue_type glossary_violation (default) or machine_translation_suspect
  severity   high/medium/low (default medium)
The target-language column may be named after any locale (kk, uz, ...).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

FLAGS = re.IGNORECASE | re.UNICODE
WORD = r"[\wЀ-ӿ]"


@dataclass
class Term:
    ru: str
    target: str
    en: str
    comment: str
    ru_re: re.Pattern
    ok_re: re.Pattern | None
    avoid_re: re.Pattern | None
    strict: bool
    issue_type: str
    severity: str


def _stem_pattern(text: str) -> str:
    parts = []
    for w in re.findall(r"[\wЀ-ӿ]+", text):
        stem = w[:-2] if len(w) >= 6 else (w[:-1] if len(w) >= 4 else w)
        parts.append(re.escape(stem) + WORD + "*")
    return rf"(?<!{WORD})" + r"\s+".join(parts) if parts else re.escape(text)


def load_glossary(path: str | Path, target_lang: str = "kk") -> list[Term]:
    terms = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        tgt = r.get(target_lang, "") or r.get("target", "")
        ru = r.get("ru", "")
        if not ru:
            continue
        ru_pat = r.get("ru_match") or _stem_pattern(ru.split("(")[0].split("/")[0])
        ok_pat = r.get(f"{target_lang}_match") or r.get("kk_match") or (
            _stem_pattern(tgt.split("(")[0].split("/")[0]) if tgt else "")
        avoid = r.get(f"{target_lang}_avoid") or r.get("kk_avoid") or ""
        terms.append(Term(
            ru=ru, target=tgt, en=r.get("en", ""), comment=r.get("comment", ""),
            ru_re=re.compile(ru_pat, FLAGS),
            ok_re=re.compile(ok_pat, FLAGS) if ok_pat else None,
            avoid_re=re.compile(avoid, FLAGS) if avoid else None,
            strict=r.get("strict", "").lower() in ("yes", "y", "true", "1", "да"),
            issue_type=r.get("issue_type") or "glossary_violation",
            severity=r.get("severity") or "medium",
        ))
    return terms
