import pytest
from locqa import icu
from locqa.arb import load_arb
from conftest import FIX


def test_duplicates_keep_every_occurrence_and_last_wins():
    a = load_arb(FIX / "tgt_kk.arb")
    occ = a.occurrences("cancel")
    assert [e.value for e in occ] == ["Бас тарту", "БАСТАУ"]
    assert a.value("cancel") == "БАСТАУ"          # Dart's jsonDecode keeps the last one
    assert occ[0].line == 4 and occ[1].line == 5
    assert len(a.occurrences("@@comment")) == 2


def test_sections_and_locale():
    a = load_arb(FIX / "src_ru.arb")
    assert a.locale == "ru"
    assert a.entry("missingOne").section == "SHOP"
    assert a.metadata("itemsCount") == {"placeholders": {"count": {}}}


def test_icu_plural_and_placeholders():
    nodes = icu.parse("{count, plural, =0{нет} one{{count} зат} other{{count} зат}} {name}")
    args = icu.arguments(nodes)
    assert [a.name for a in args] == ["count", "count", "count", "name"]
    assert set(args[0].options) == {"=0", "one", "other"}


@pytest.mark.parametrize("bad", ["{name", "Сәлем}", "{count, plural, one{x}", "{1}"])
def test_icu_errors(bad):
    with pytest.raises(icu.IcuError):
        icu.parse(bad)


def test_apostrophes_are_literal():
    assert icu.placeholder_names("<font color='#FFFFFF'>{x}</font>") == ["x"]
