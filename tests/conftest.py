from pathlib import Path
import pytest
from locqa.arb import load_arb
from locqa.checks import Context
from locqa.glossary import load_glossary

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def ctx():
    return Context(load_arb(FIX / "src_ru.arb"), load_arb(FIX / "tgt_kk.arb"),
                   [load_arb(FIX / "ref_uz.arb")], load_glossary(FIX / "glossary.csv"), "kk")


def kinds(issues, key):
    return {i.issue_type for i in issues if i.key == key}
