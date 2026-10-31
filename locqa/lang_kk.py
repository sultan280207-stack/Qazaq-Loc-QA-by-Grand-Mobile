"""Kazakh-specific knowledge: alphabet, look-alike letters, affixes, harmony,
official Latin transliteration (2021 alphabet)."""
from __future__ import annotations

import re

KAZAKH_ONLY = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
FRONT = set("әеөүіэ")
BACK = set("аоұыяё")
# Russian letter a typist uses instead of the Kazakh one
LOOKALIKE = {"а": "ә", "г": "ғ", "к": "қ", "н": "ң", "о": "ө", "у": "ұү", "и": "і", "х": "һ"}
# Latin letters that look like Cyrillic ones
HOMOGLYPHS = {"a": "а", "c": "с", "e": "е", "i": "і", "o": "о", "p": "р", "x": "х", "y": "у",
              "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "I": "І", "K": "К", "M": "М",
              "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У"}

# case / derivational affixes whose vowel and first consonant depend on the stem
AFFIXES = ["ға", "ге", "қа", "ке", "на", "не", "а", "е",
           "да", "де", "та", "те", "нда", "нде",
           "дан", "ден", "тан", "тен", "нан", "нен",
           "ны", "ні", "ды", "ді", "ты", "ті", "н",
           "ның", "нің", "дың", "дің", "тың", "тің",
           "мен", "бен", "пен",
           "дағы", "дегі", "тағы", "тегі",
           "лар", "лер", "дар", "дер", "тар", "тер",
           "ша", "ше", "ші", "шы", "ыншы", "інші", "нші", "ншы"]
_AFFIX_RE = "|".join(sorted(AFFIXES, key=len, reverse=True))
# placeholder immediately followed by an affix: {name}-ға, %s-ге, {n}'ге, {x}ға
PLACEHOLDER_AFFIX = re.compile(
    r"(\{[A-Za-z_][A-Za-z0-9_]*\}|%\d*\$?[sd]\d?)([-‑–'’]?)(" + _AFFIX_RE + r")(?![\wЀ-ӿ])")
# ordinal "-ші/-шы" and "-деңгей", "-орын" after numbers are fine in Kazakh writing
ORDINAL_OK = {"ші", "шы", "інші", "ыншы", "нші", "ншы"}

# case meaning -> postposition that does not need harmony
AFFIX_CASE = {
    **dict.fromkeys(["ға", "ге", "қа", "ке", "на", "не", "а", "е"], "dative"),
    **dict.fromkeys(["да", "де", "та", "те", "нда", "нде"], "locative"),
    **dict.fromkeys(["дан", "ден", "тан", "тен", "нан", "нен"], "ablative"),
    **dict.fromkeys(["ны", "ні", "ды", "ді", "ты", "ті", "н"], "accusative"),
    **dict.fromkeys(["ның", "нің", "дың", "дің", "тың", "тің"], "genitive"),
    **dict.fromkeys(["мен", "бен", "пен"], "instrumental"),
}


def vowel_class(s: str) -> str | None:
    """Class of the last unambiguous vowel: 'F' front, 'B' back."""
    for ch in reversed(s.lower()):
        if ch in FRONT:
            return "F"
        if ch in BACK:
            return "B"
    return None


def affix_class(affix: str) -> str | None:
    return vowel_class(affix)


# ---------------------------------------------------------------------------
# Official Latin alphabet (April 2021 revision, 31 letters): И/Й -> İ i,
# І -> I ı, Ы -> Y y, Ң -> Ñ ñ, Ш -> Ş ş. Letters used only in Russian loanwords
# (Ё Ц Ч Щ Ъ Ь Э Ю Я) have no official letter; they are mapped by common
# practice (ts, ch, şş, io, iu, ia) and documented as such.
CYR2LAT = {
    "а": "a", "ә": "ä", "б": "b", "в": "v", "г": "g", "ғ": "ğ", "д": "d", "е": "e",
    "ё": "io", "ж": "j", "з": "z", "и": "i", "й": "i", "к": "k", "қ": "q", "л": "l",
    "м": "m", "н": "n", "ң": "ñ", "о": "o", "ө": "ö", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ұ": "ū", "ү": "ü", "ф": "f", "х": "h", "һ": "h", "ц": "ts",
    "ч": "ch", "ш": "ş", "щ": "şş", "ъ": "", "ы": "y", "і": "ı", "ь": "", "э": "e",
    "ю": "iu", "я": "ia",
}


def transliterate(text: str) -> str:
    """Kazakh Cyrillic -> Latin (2021). Placeholders and tags are kept as is."""
    out, i = [], 0
    protected = re.compile(r"\{[^{}]*\}|<[^>]*>|%\d*\$?[sd]\d?")
    for m in protected.finditer(text):
        out.append(_tr(text[i:m.start()]))
        out.append(m.group(0))
        i = m.end()
    out.append(_tr(text[i:]))
    return "".join(out)


def _tr(s: str) -> str:
    res = []
    for idx, ch in enumerate(s):
        low = ch.lower()
        if low not in CYR2LAT:
            res.append(ch)
            continue
        lat = CYR2LAT[low]
        if ch.isupper() and lat:
            nxt = s[idx + 1] if idx + 1 < len(s) else ""
            word_caps = nxt.isupper() or (idx > 0 and s[idx - 1].isupper())
            if low in "ий":
                lat = "İ"
            else:
                lat = lat.upper() if word_caps else lat[0].upper() + lat[1:]
        res.append(lat)
    return "".join(res)
