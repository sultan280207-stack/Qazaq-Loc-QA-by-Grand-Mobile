import csv, json
from locqa.cli import main
from locqa.arb import load_arb
from locqa.validate import validate
from locqa.lang_kk import transliterate
from conftest import FIX


def run_check(tmp_path, review=None):
    out = tmp_path / "report.json"
    args = ["check", "--source", str(FIX / "src_ru.arb"), "--target", str(FIX / "tgt_kk.arb"),
            "--glossary", str(FIX / "glossary.csv"), "--ref", str(FIX / "ref_uz.arb"), "--out", str(out)]
    if review:
        args += ["--review", str(review)]
    assert main(args) == 0
    return json.loads(out.read_text(encoding="utf-8"))


def test_check_writes_json_and_html(tmp_path):
    data = run_check(tmp_path)
    assert (tmp_path / "report.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    assert all(d["reviewed_by_human"] is False for d in data)
    assert {d["issue_type"] for d in data} >= {"untranslated", "placeholder_mismatch", "suffix_harmony",
                                               "wrong_language", "same_as_source", "orthography"}


def test_review_reject_confirm_add(tmp_path):
    rev = tmp_path / "review.csv"
    with open(rev, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "issue_type", "verdict", "severity", "suggestion", "evidence", "reviewed_by_human", "reviewer", "note"])
        w.writerow(["shopTab", "length_overflow", "confirm", "", "Дүкенге", "", "true", "Айгерім", ""])
        w.writerow(["unknownError", "same_as_source", "reject", "", "", "", "true", "Айгерім", ""])
        w.writerow(["missingOne", "untranslated", "add", "high", "Жоқ жол", "Нет ключа", "false", "", ""])
    data = run_check(tmp_path, rev)
    by = {(d["key"], d["issue_type"]): d for d in data}
    assert by[("shopTab", "length_overflow")]["reviewed_by_human"] is True
    assert by[("shopTab", "length_overflow")]["suggestion"] == "Дүкенге"
    assert ("unknownError", "same_as_source") not in by


def test_fix_writes_valid_arb_with_flags(tmp_path):
    run_check(tmp_path)
    fixed = tmp_path / "fixed.arb"
    main(["fix", "--source", str(FIX / "src_ru.arb"), "--target", str(FIX / "tgt_kk.arb"),
          "--report", str(tmp_path / "report.json"), "--out", str(fixed)])
    a = load_arb(fixed)
    assert a.value("greeting") == "Сәлем, {name}!"
    assert a.metadata("greeting")["x-reviewed_by_human"] is False
    assert a.metadata("greeting")["x-locqa-original"] == "Сәлем, name!"
    assert a.value("buyFor") == "{price} үшін сатып алу"
    assert a.occurrences("cancel")[0].value == "Бас тарту"   # only the effective occurrence edited
    # the broken plural has no automatic fix, so it is the only thing left for gen-l10n to reject
    assert validate(load_arb(FIX / "src_ru.arb"), a) == ["itemsCount: plural 'count' has no 'other' case"]


def test_validate_catches_errors(tmp_path):
    bad = tmp_path / "bad.arb"
    bad.write_text('{"greeting": "Сәлем, {name!", "buyFor": "{cost} үшін"}', encoding="utf-8")
    errs = validate(load_arb(FIX / "src_ru.arb"), load_arb(bad))
    assert any("ICU" in e for e in errs) and any("cost" in e for e in errs)


def test_transliteration_2021():
    assert transliterate("Қазақстан Республикасы") == "Qazaqstan Respublikasy"
    assert transliterate("ІШКІ {name} сыйлық Иә") == "IŞKI {name} syilyq İä"


def _review(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "issue_type", "verdict", "severity", "suggestion", "evidence", "reviewed_by_human", "reviewer", "note"])
        w.writerows(rows)


def test_later_review_file_wins(tmp_path):
    expert, native = tmp_path / "expert.csv", tmp_path / "native.csv"
    _review(expert, [["missingOne", "untranslated", "add", "high", "Жоқ жол", "Нет ключа", "false", "", ""],
                     ["unknownError", "same_as_source", "reject", "", "", "", "false", "", ""],
                     ["shopTab", "length_overflow", "confirm", "", "Дүкенге", "", "false", "", ""]])
    _review(native, [["missingOne", "untranslated", "reject", "", "", "", "true", "Айгерім", "так и задумано"],
                     ["shopTab", "length_overflow", "confirm", "", "Дүкен", "", "true", "Айгерім", ""]])
    out = tmp_path / "report.json"
    assert main(["check", "--source", str(FIX / "src_ru.arb"), "--target", str(FIX / "tgt_kk.arb"),
                 "--glossary", str(FIX / "glossary.csv"), "--review", str(expert), "--review", str(native),
                 "--out", str(out)]) == 0
    by = {(d["key"], d["issue_type"]): d for d in json.loads(out.read_text(encoding="utf-8"))}
    assert ("missingOne", "untranslated") not in by            # native rejected the expert's addition
    assert ("unknownError", "same_as_source") not in by        # expert's reject survives
    assert by[("shopTab", "length_overflow")]["suggestion"] == "Дүкен"
    assert by[("shopTab", "length_overflow")]["reviewed_by_human"] is True


def test_fix_updates_every_duplicate(tmp_path):
    rev = tmp_path / "review.csv"
    _review(rev, [["cancel", "inconsistent_term", "confirm", "", "Бас тарту", "", "true", "Айгерім", ""]])
    run_check(tmp_path, rev)
    fixed = tmp_path / "fixed.arb"
    main(["fix", "--source", str(FIX / "src_ru.arb"), "--target", str(FIX / "tgt_kk.arb"),
          "--report", str(tmp_path / "report.json"), "--out", str(fixed)])
    a = load_arb(fixed)
    assert [e.value for e in a.occurrences("cancel")] == ["Бас тарту", "Бас тарту"]
    assert len(a.occurrences("@cancel")) == 1
    assert a.metadata("cancel")["x-reviewed_by_human"] is True


def test_review_page(tmp_path):
    run_check(tmp_path)
    page = tmp_path / "review.html"
    assert main(["review-page", "--report", str(tmp_path / "report.json"), "--out", str(page),
                 "--name", "tgt_kk.arb"]) == 0
    text = page.read_text(encoding="utf-8")
    assert "Проверка правок tgt_kk.arb" in text and "greeting" in text and "native_review.csv" in text
