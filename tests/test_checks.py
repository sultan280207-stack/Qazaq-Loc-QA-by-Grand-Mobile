from locqa.checks import (check_untranslated, check_same_as_source, check_placeholders, check_plurals,
                          check_glossary, check_length, check_suffix_harmony, check_orthography,
                          check_wrong_language, check_inconsistent, check_mt_suspect, rephrase_affix, run_checks)
from conftest import kinds


def test_untranslated(ctx):
    iss = check_untranslated(ctx)
    assert [i.key for i in iss] == ["missingOne"]
    assert "uz" in iss[0].evidence


def test_same_as_source_skips_loanwords(ctx):
    keys = {i.key for i in check_same_as_source(ctx)}
    assert "unknownError" in keys
    assert "sameLoan" not in keys          # «Финал» is used inside other Kazakh strings


def test_placeholders(ctx):
    iss = {i.key: i for i in check_placeholders(ctx)}
    assert iss["greeting"].suggestion == "Сәлем, {name}!"
    assert iss["level"].suggestion == "{level} деңгей қажет"


def test_plurals(ctx):
    iss = check_plurals(ctx)
    assert any(i.key == "itemsCount" and "other" in i.evidence for i in iss)


def test_glossary(ctx):
    iss = check_glossary(ctx)
    assert kinds(iss, "family") == {"glossary_violation"}
    assert kinds(iss, "cancel") == {"machine_translation_suspect"}


def test_length_and_padding_tail(ctx):
    iss = {i.key: i for i in check_length(ctx)}
    assert "shopTab" in iss and iss["shopTab"].severity == "high"
    assert iss["shopTab"].suggestion == "Дүкенге өту"
    assert "shopButton" not in iss


def test_suffix_after_placeholder(ctx):
    iss = {i.key: i for i in check_suffix_harmony(ctx)}
    assert set(iss) == {"buyFor", "playerFrom"}
    assert iss["buyFor"].suggestion == "{price} үшін сатып алу"
    assert iss["playerFrom"].severity == "high"


def test_rephrase_rules():
    assert rephrase_affix("{max}-нан көп сатып алуға болмайды") == "Ең көбі {max} сатып алуға болады"
    assert rephrase_affix("{name}-ға хабарлама") is None


def test_orthography(ctx):
    iss = {i.key: i for i in check_orthography(ctx)}
    assert iss["time"].suggestion == "6 сағат сайын 1 рет"
    assert "comment3" not in iss  # «пікір» occurs only twice: too rare to be sure


def test_wrong_language(ctx):
    iss = {i.key: i for i in check_wrong_language(ctx)}
    assert "узбек" in iss["authError"].evidence
    assert "португал" in iss["deleteConfirm"].evidence


def test_inconsistent(ctx):
    iss = check_inconsistent(ctx)
    assert any(i.key == "cancel" and i.extra == {} and "строки" in i.evidence for i in iss)


def test_numbers_changed(ctx):
    iss = check_mt_suspect(ctx)
    assert any(i.key == "adLength" and i.detector == "numbers" for i in iss)


def test_run_all_is_sorted_and_schema(ctx):
    iss = run_checks(ctx)
    d = iss[0].to_json()
    for f in ("key", "issue_type", "severity", "source", "target", "evidence", "suggestion",
              "confidence", "reviewed_by_human"):
        assert f in d
    sev = [i.severity for i in iss]
    assert sev == sorted(sev, key=["high", "medium", "low"].index)
