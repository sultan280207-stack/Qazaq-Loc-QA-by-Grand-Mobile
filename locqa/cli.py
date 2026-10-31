"""Command line interface.

  locqa check    --source intl_ru.arb --target intl_kk.arb --glossary glossary.csv --out report.json
  locqa fix      --source intl_ru.arb --target intl_kk.arb --report report.json --out intl_kk_fixed.arb
  locqa validate --template intl_ru.arb intl_kk_fixed.arb
  locqa translit --target intl_kk.arb --out report_latin.json
  locqa review-page --report report.json --out review.html
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import __version__
from .arb import load_arb
from .checks import Context, run_checks, visible
from .fixer import plan_changes, write_fixed
from .glossary import load_glossary
from .issues import Issue, ISSUE_TYPES
from .report_html import render
from .review import apply_review, export_review_sheet, load_review, merge_reviews
from .review_page import render_review_page
from .validate import validate


def _ctx(a) -> Context:
    src, tgt = load_arb(a.source), load_arb(a.target)
    refs = [load_arb(r) for r in (a.ref or [])]
    lang = a.lang or (tgt.locale or "").split("_")[0] or "kk"
    gloss = load_glossary(a.glossary, lang) if a.glossary else []
    return Context(src, tgt, refs, gloss, lang)


def cmd_check(a) -> int:
    ctx = _ctx(a)
    only = set(a.only.split(",")) if a.only else None
    issues = run_checks(ctx, only)
    stats = {}
    if a.review:
        rows = merge_reviews(*(load_review(p) for p in a.review))
        issues, stats = apply_review(issues, rows, ctx)
    order = {"high": 0, "medium": 1, "low": 2}
    min_rank = order[a.min_severity]
    issues = [i for i in issues if order[i.severity] <= min_rank]
    issues.sort(key=lambda i: (order[i.severity], ISSUE_TYPES.index(i.issue_type), i.line or 0, i.key))
    data = [i.to_json() for i in issues]
    Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    nm = lambda x: Path(x).name if x else "—"
    meta = {"source": nm(a.source), "target": nm(a.target), "refs": ", ".join(nm(r) for r in a.ref or []) or "—",
            "glossary": nm(a.glossary), "review": ", ".join(nm(r) for r in a.review or []) or "—",
            "generated": dt.datetime.now().strftime("%d.%m.%Y"), "version": __version__}
    html_path = a.html or str(Path(a.out).with_suffix(".html"))
    Path(html_path).write_text(render(data, meta), encoding="utf-8")
    if a.review_sheet:
        export_review_sheet(issues, a.review_sheet)
    counts = {}
    for i in issues:
        counts[i.issue_type] = counts.get(i.issue_type, 0) + 1
    print(f"locqa {__version__}: {len(issues)} issues -> {a.out}, {html_path}")
    for t in ISSUE_TYPES:
        if counts.get(t):
            print(f"  {t:30} {counts[t]}")
    if stats:
        print("  review:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    if a.fail_on:
        bad = [i for i in issues if order[i.severity] <= order[a.fail_on]]
        return 1 if bad else 0
    return 0


def cmd_fix(a) -> int:
    src, tgt = load_arb(a.source), load_arb(a.target)
    raw = json.loads(Path(a.report).read_text(encoding="utf-8"))
    issues = [Issue(d["key"], d["issue_type"], d["severity"], d.get("source"), d.get("target"),
                    d.get("evidence", ""), d.get("suggestion"), d.get("confidence", 0.5),
                    bool(d.get("reviewed_by_human")), d.get("line"), d.get("detector", ""),
                    d.get("origin", "auto")) for d in raw]
    if a.only_reviewed:
        issues = [i for i in issues if i.reviewed_by_human]
    plan = plan_changes(issues, src, tgt)
    res = write_fixed(src, tgt, plan, a.out)
    errs = validate(src, load_arb(a.out))
    print(f"{a.out}: changed {res['changed']}, added {res['added']}; "
          f"reviewed_by_human: {res['reviewed']}, not reviewed: {res['unreviewed']}; validation errors: {len(errs)}")
    for e in errs[:20]:
        print("  ", e)
    return 1 if errs else 0


def cmd_validate(a) -> int:
    errs = validate(load_arb(a.template), load_arb(a.arb))
    for e in errs:
        print(e)
    print(f"{a.arb}: {len(errs)} errors")
    return 1 if errs else 0


def cmd_review_page(a) -> int:
    raw = json.loads(Path(a.report).read_text(encoding="utf-8"))
    if a.only_with_fix:
        keys = {d["key"] for d in raw if d.get("suggestion")}
        raw = [d for d in raw if d["key"] in keys]
    Path(a.out).write_text(render_review_page(raw, a.name or ""), encoding="utf-8")
    print(f"{a.out}: {len({d['key'] for d in raw})} strings to review")
    return 0


def cmd_translit(a) -> int:
    from .lang_kk import transliterate
    tgt = load_arb(a.target)
    out, long_ = {}, []
    for k, v in tgt.messages().items():
        lat = transliterate(v)
        out[k] = lat
        lc, ll = len(visible(v)), len(visible(lat))
        if lc and ll / lc > a.max_ratio and ll - lc >= 3:
            long_.append({"key": k, "cyrillic": v, "latin": lat, "len_cyrillic": lc, "len_latin": ll,
                          "ratio": round(ll / lc, 2)})
    if a.out_arb:
        body = {"@@locale": "kk_Latn", **out}
        Path(a.out_arb).write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(a.out).write_text(json.dumps(long_, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(out)} strings transliterated; {len(long_)} grow more than x{a.max_ratio} -> {a.out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="locqa", description="Localization QA for Flutter ARB files")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="find issues and write report.json + HTML")
    c.add_argument("--source", required=True)
    c.add_argument("--target", required=True)
    c.add_argument("--glossary")
    c.add_argument("--ref", action="append", help="other translations of the same file (e.g. intl_uz.arb); repeatable")
    c.add_argument("--review", action="append",
                   help="reviewer verdicts CSV (confirm / reject / add); repeatable, later files win")
    c.add_argument("--out", required=True)
    c.add_argument("--html")
    c.add_argument("--lang", help="target language code (default: @@locale of the target)")
    c.add_argument("--only", help="comma-separated issue types")
    c.add_argument("--min-severity", choices=["high", "medium", "low"], default="low")
    c.add_argument("--review-sheet", help="also export a CSV for human review")
    c.add_argument("--fail-on", choices=["high", "medium", "low"], help="exit 1 if issues of this severity or worse")
    c.set_defaults(fn=cmd_check)

    f = sub.add_parser("fix", help="apply suggestions from a report and write a fixed ARB")
    f.add_argument("--source", required=True)
    f.add_argument("--target", required=True)
    f.add_argument("--report", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--only-reviewed", action="store_true", help="apply only findings reviewed by a human")
    f.set_defaults(fn=cmd_fix)

    v = sub.add_parser("validate", help="gen-l10n-style validation of an ARB against its template")
    v.add_argument("--template", required=True)
    v.add_argument("arb")
    v.set_defaults(fn=cmd_validate)

    t = sub.add_parser("translit", help="Kazakh Cyrillic -> Latin (2021) with length check")
    t.add_argument("--target", required=True)
    t.add_argument("--out", required=True, help="JSON list of strings that grow too much")
    t.add_argument("--out-arb", help="also write the transliterated ARB")
    t.add_argument("--max-ratio", type=float, default=1.15)
    t.set_defaults(fn=cmd_translit)

    r = sub.add_parser("review-page", help="offline HTML page for a native speaker; exports a --review CSV")
    r.add_argument("--report", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--name", help="file name shown in the title, e.g. intl_kk.arb")
    r.add_argument("--only-with-fix", action="store_true", help="only strings that have a suggested fix")
    r.set_defaults(fn=cmd_review_page)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
