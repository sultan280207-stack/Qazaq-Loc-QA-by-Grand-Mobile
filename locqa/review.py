"""Human-in-the-loop: merge reviewer verdicts into the automatic findings.

review CSV columns (UTF-8):
  key, issue_type, verdict, severity, suggestion, evidence, reviewed_by_human, reviewer, note
verdict:
  confirm  keep the automatic finding (key, issue_type); non-empty columns override it
  reject   drop the automatic finding(s) with this (key, issue_type) - false positive
  add      a finding the tool did not produce (expert / manual review)
reviewed_by_human must be `true` only when a person actually checked the row.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .issues import Issue, ISSUE_TYPES, SEVERITIES

COLUMNS = ["key", "issue_type", "verdict", "severity", "suggestion", "evidence",
           "reviewed_by_human", "reviewer", "note"]
TRUE = {"true", "yes", "1", "да", "y"}


def load_review(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [{k.strip(): (v if v is not None else "") for k, v in r.items() if k} for r in csv.DictReader(f)]
    for r in rows:
        r["verdict"] = r.get("verdict", "").strip().lower()
        if r["verdict"] not in ("confirm", "reject", "add"):
            raise ValueError(f"review: bad verdict {r['verdict']!r} for {r.get('key')}")
        if r.get("issue_type") not in ISSUE_TYPES:
            raise ValueError(f"review: bad issue_type {r.get('issue_type')!r} for {r.get('key')}")
        if r.get("severity") and r["severity"] not in SEVERITIES:
            raise ValueError(f"review: bad severity {r['severity']!r} for {r.get('key')}")
    return rows


def merge_reviews(*sheets: list[dict]) -> list[dict]:
    """Several review files applied in order: a later row for the same (key, issue_type)
    replaces the earlier one. Typical use: the expert sheet first, the native speaker's last."""
    merged: dict[tuple, dict] = {}
    for rows in sheets:
        for r in rows:
            ident = (r["key"], r["issue_type"])
            merged.pop(ident, None)
            merged[ident] = r
    return list(merged.values())


def apply_review(issues: list[Issue], rows: list[dict], ctx) -> tuple[list[Issue], dict]:
    by_id: dict[tuple, list[Issue]] = {}
    for i in issues:
        by_id.setdefault(i.ident, []).append(i)
    stats = {"confirmed": 0, "rejected": 0, "added": 0, "unmatched_confirm": 0}
    rejected = set()
    added: list[Issue] = []
    for r in rows:
        ident = (r["key"], r["issue_type"])
        human = str(r.get("reviewed_by_human", "")).strip().lower() in TRUE
        if r["verdict"] == "reject":
            if ident in by_id:
                rejected.add(ident); stats["rejected"] += 1
            continue
        if r["verdict"] == "confirm" and ident in by_id:
            for i in by_id[ident]:
                _override(i, r, human)
            stats["confirmed"] += 1
            continue
        if r["verdict"] == "confirm":
            stats["unmatched_confirm"] += 1
        # add (or a confirm the tool did not produce): build a new finding
        s, t = ctx.src.get(r["key"]), ctx.tgt.get(r["key"])
        e = ctx.target.entry(r["key"])
        sev = r.get("severity") or "medium"
        iss = Issue(r["key"], r["issue_type"], sev, s, t, r.get("evidence") or r.get("note") or "",
                    r.get("suggestion") or None, 0.9, human, e.line if e else None, "expert_review", "review")
        added.append(iss)
        stats["added"] += 1
    out = [i for i in issues if i.ident not in rejected] + added
    return out, stats


def _override(i: Issue, r: dict, human: bool) -> None:
    if r.get("severity"):
        i.severity = r["severity"]
    if r.get("suggestion"):
        i.suggestion = r["suggestion"]
    if r.get("evidence"):
        i.evidence = r["evidence"]
    i.reviewed_by_human = human
    i.confidence = max(i.confidence, 0.9)
    i.origin = "auto+review"


def export_review_sheet(issues: list[Issue], path: str | Path) -> None:
    """CSV for a native speaker: one row per finding, verdict to fill in."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS + ["source", "target", "line"])
        for i in issues:
            w.writerow([i.key, i.issue_type, "confirm" if i.origin != "auto" else "",
                        i.severity, i.suggestion or "", i.evidence,
                        "true" if i.reviewed_by_human else "false", "", "", i.source or "", i.target or "", i.line or ""])
