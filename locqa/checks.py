"""All detectors. Each one is a function (ctx) -> list[Issue].

Language-independent detectors run for any ARB pair.  Detectors that need
Kazakh morphology (look-alike letters, harmony, placeholder affixes) run when
the target locale is `kk`; other locales get the generic set.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import icu, lang_kk
from .arb import ArbFile
from .glossary import Term
from .issues import Issue

CYR = re.compile(r"[Ѐ-ӿ]")
LAT = re.compile(r"[A-Za-zÀ-ɏ]")
TOKEN = re.compile(r"[\wЀ-ӿ]+(?:[-‑][\wЀ-ӿ]+)*")
MARKUP = re.compile(r"\{[^{}]*\}|%\d*\$?[sd]\d?|<[^>]+>|https?://\S+|#[0-9A-Fa-f]{6}")
UI_KEY_HINT = re.compile(r"(button|btn|tab|title|header|label|caption|name|menu|action|cancel|"
                         r"confirm|buy|ok|close|back|next|apply|select|choose|prefix|suffix|short)", re.I)
CYRILLIC_LOCALES = {"kk", "ru", "uk", "be", "ky", "tg", "mn", "bg", "sr", "mk", "tt", "ba"}


def visible(text: str) -> str:
    """Text without placeholders, tags and URLs."""
    return MARKUP.sub("", text or "")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "").casefold()
    t = re.sub(r"[\s  ]+", " ", t).strip()
    return t.strip(" .,!?:;…—-–")


def words(text: str) -> list[str]:
    return TOKEN.findall(visible(text))


def trigrams(text: str) -> set[str]:
    t = " " + norm(visible(text)) + " "
    return {t[i:i + 3] for i in range(len(t) - 2)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass
class Context:
    source: ArbFile
    target: ArbFile
    refs: list[ArbFile] = field(default_factory=list)
    glossary: list[Term] = field(default_factory=list)
    target_lang: str = "kk"

    def __post_init__(self):
        self.src = self.source.messages()
        self.tgt = self.target.messages()
        self.ref_msgs = [(r.locale or r.path.stem, r.messages()) for r in self.refs]
        # vocabulary of the target, counted over every occurrence
        self.vocab = Counter()
        self.translated_tokens = set()
        for k, v in self.tgt.items():
            toks = [w.lower() for w in words(v)]
            self.vocab.update(toks)
            if norm(v) != norm(self.src.get(k, "")):
                self.translated_tokens.update(toks)
        self.src_vocab = Counter(w.lower() for v in self.src.values() for w in words(v))

    def pair(self, key):
        return self.src.get(key), self.tgt.get(key)

    def line(self, key):
        e = self.target.entry(key)
        return e.line if e else None

    def issue(self, key, typ, sev, evidence, suggestion=None, conf=0.5, detector=""):
        s, t = self.pair(key)
        return Issue(key, typ, sev, s, t, evidence, suggestion, conf, False, self.line(key), detector)

    def is_kk(self):
        return (self.target_lang or "").split("_")[0] == "kk"

    def attested(self, token: str) -> bool:
        """Token (or its stem) is used inside real target-language translations."""
        t = token.lower()
        if t in self.translated_tokens:
            return True
        stem = t[:max(4, len(t) - 2)]
        return any(w.startswith(stem) and w != t for w in self.translated_tokens) if len(stem) >= 4 else False


# --------------------------------------------------------------------------
def check_untranslated(ctx: Context) -> list[Issue]:
    out = []
    for key, s in ctx.src.items():
        if key not in ctx.tgt:
            refs = [loc for loc, m in ctx.ref_msgs if key in m]
            ev = "Ключа нет в переводе"
            if refs:
                ev += f", хотя в {', '.join(refs)} он есть"
            src_line = ctx.source.entry(key).line
            out.append(Issue(key, "untranslated", "high", s, None, ev + f". В исходнике это строка {src_line}.",
                             None, 0.98, False, None, "missing_key"))
        else:
            t = ctx.tgt[key]
            if not t.strip() and s.strip() and len(words(s)) >= 3:
                sev, conf = "medium", 0.6
                out.append(ctx.issue(key, "untranslated", sev,
                    "Перевод пустой, а в исходнике текст есть. Иногда текст специально переносят в соседний ключ "
                    "(другой порядок слов), так что стоит глянуть соседей.", None, conf, "empty_value"))
    return out


def check_same_as_source(ctx: Context) -> list[Issue]:
    out = []
    for key, t in ctx.tgt.items():
        s = ctx.src.get(key)
        if s is None or norm(s) != norm(t) or not norm(t):
            continue
        toks = [w for w in words(s) if CYR.search(w)]
        if not toks:
            continue  # brands, numbers, Latin-only names
        real = [w for w in toks if len(w) >= 3 and not w.isdigit()]
        unattested = [w for w in real if not ctx.attested(w)]
        if not unattested:
            continue  # loanwords used the same way in the target language
        func = [w for w in toks if w.lower() in RU_FUNCTION_WORDS]
        morph = [w for w in unattested if RU_MORPH.search(w.lower()) and not
                 (w[:1].isupper() and w.lower().endswith("ия") and len(toks) == 1)]
        if not (func or morph or len(unattested) >= 3):
            continue  # single loanwords and character names are legitimate
        n = len(real)
        sev, conf = (("high", 0.95) if n >= 3 else ("medium", 0.85) if n == 2 else ("medium", 0.75))
        ev = (f"Тут стоит тот же текст, что в исходнике. Слова {', '.join('«'+w+'»' for w in unattested[:4])} "
              f"больше нигде в переводе не встречаются, значит это не привычное заимствование.")
        out.append(ctx.issue(key, "same_as_source", sev, ev, None, conf, "identical_to_source"))
    return out


RU_FUNCTION_WORDS = set("""и в во на для не что это с со по от за к из у или как все вы ты мы уже еще ещё
будет можно нужно чтобы если при до после через ваш ваши твой свой его её их она он они был
была было быть есть нет да а но же только очень более менее об о чем тем""".split())
RU_MORPH = re.compile(r"(ть|ться|ешь|ет|ют|ят|ит|ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|ых|их|"
                      r"ами|ями|ах|ях|ей|ов|ья|им|ена|ено)$")


# --------------------------------------------------------------------------
PRINTF = re.compile(r"%\d*\$?[sd]\d?")
TAG = re.compile(r"</?[A-Za-z][^>]*>")


def _icu_args(text):
    try:
        return icu.arguments(icu.parse(text)), None
    except icu.IcuError as e:
        return None, str(e)


def check_placeholders(ctx: Context) -> list[Issue]:
    out = []
    for key, t in ctx.tgt.items():
        s = ctx.src.get(key)
        if s is None or not t:
            continue
        sa, serr = _icu_args(s)
        ta, terr = _icu_args(t)
        if terr and not serr:
            out.append(ctx.issue(key, "placeholder_mismatch", "high",
                f"Перевод не разбирается как ICU ({terr}), gen-l10n такой файл не соберёт.",
                None, 0.95, "icu_syntax"))
            continue
        problems, suggestion = [], t
        if sa is not None and ta is not None:
            sn = Counter(a.name for a in sa if not a.is_complex)
            tn = Counter(a.name for a in ta if not a.is_complex)
            missing = sn - tn
            extra = tn - sn
            for name in list(missing):
                # name present as a bare word -> braces were lost
                bare = re.search(rf"(?<![\w{{]){re.escape(name)}(?![\w}}])", suggestion)
                close = [e for e in extra if _edit1(e, name)]
                if close:
                    problems.append(f"{{{close[0]}}} вместо {{{name}}}")
                    suggestion = suggestion.replace("{" + close[0] + "}", "{" + name + "}", 1)
                    extra[close[0]] -= 1
                elif bare:
                    problems.append(f"у {{{name}}} пропали фигурные скобки (в тексте просто «{name}»)")
                    suggestion = suggestion[:bare.start()] + "{" + name + "}" + suggestion[bare.end():]
                else:
                    problems.append(f"пропал {{{name}}}")
                    suggestion = None if suggestion == t else suggestion
            for name, n in (+extra).items():
                problems.append(f"лишний {{{name}}}")
        sp, tp = Counter(PRINTF.findall(s)), Counter(PRINTF.findall(t))
        if sp != tp:
            problems.append(f"%-плейсхолдеры: в исходнике {sorted(sp.elements())}, в переводе {sorted(tp.elements())}")
            suggestion = None
        st, tt = Counter(TAG.findall(s)), Counter(TAG.findall(t))
        stn, ttn = Counter(_tagname(x) for x in st.elements()), Counter(_tagname(x) for x in tt.elements())
        if stn != ttn:
            problems.append(f"теги: в исходнике {dict(stn)}, в переводе {dict(ttn)}")
            suggestion = None
        if problems:
            if suggestion == t:
                suggestion = None
            out.append(ctx.issue(key, "placeholder_mismatch", "high",
                "Не сходятся плейсхолдеры: " + "; ".join(problems) + ".",
                suggestion, 0.97, "placeholders"))
    return out


def _tagname(tag):
    m = re.match(r"</?\s*([A-Za-z]+)", tag)
    return ("/" if tag.startswith("</") else "") + (m.group(1).lower() if m else tag)


def _edit1(a: str, b: str) -> bool:
    if a == b or abs(len(a) - len(b)) > 2:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long_ = sorted((a, b), key=len)
    return long_.startswith(short) or long_.endswith(short) or any(
        long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def check_plurals(ctx: Context) -> list[Issue]:
    out = []
    lang = (ctx.target_lang or "").split("_")[0]
    allowed = icu.CLDR_CARDINAL.get(lang)
    for key, t in ctx.tgt.items():
        s = ctx.src.get(key)
        if s is None:
            continue
        sa, _ = _icu_args(s)
        ta, terr = _icu_args(t)
        s_pl = {a.name: a for a in (sa or []) if a.kind in ("plural", "selectordinal")}
        if terr and s_pl:
            out.append(ctx.issue(key, "plural_mismatch", "high",
                f"Сломан ICU-плюрал: {terr}.", None, 0.95, "plural_syntax"))
            continue
        if ta is None:
            continue
        t_pl = {a.name: a for a in ta if a.kind in ("plural", "selectordinal")}
        for name, a in s_pl.items():
            if name not in t_pl:
                out.append(ctx.issue(key, "plural_mismatch", "high",
                    f"В исходнике есть {{{name}, {a.kind}, …}}, а в переводе её нет.",
                    None, 0.9, "plural_missing"))
                continue
            ta_ = t_pl[name]
            cats = set(ta_.options)
            if "other" not in cats:
                out.append(ctx.issue(key, "plural_mismatch", "high",
                    f"В {{{name}, plural}} нет обязательной формы other (есть только {', '.join(sorted(cats))}).",
                    None, 0.95, "plural_other"))
            if allowed and a.kind == "plural":
                kw = {c for c in cats if not c.startswith("=")}
                unknown = kw - icu.PLURAL_CATEGORIES
                if unknown:
                    out.append(ctx.issue(key, "plural_mismatch", "high",
                        f"Непонятные формы {sorted(unknown)} в {{{name}, plural}}.", None, 0.9, "plural_category"))
                needed = allowed - kw - {"other"}
                if needed and not any(c.startswith("=") for c in cats):
                    out.append(ctx.issue(key, "plural_mismatch", "low",
                        f"Для {lang} по CLDR нужны формы {sorted(allowed)}, не хватает {sorted(needed)}.",
                        None, 0.5, "plural_incomplete"))
            # placeholders used inside each option should match source's "other"
            src_inner = {x.name for x in icu.arguments(a.options.get("other", []))}
            for sel, body in ta_.options.items():
                inner = {x.name for x in icu.arguments(body)}
                if inner - src_inner - {name}:
                    out.append(ctx.issue(key, "plural_mismatch", "medium",
                        f"В форме '{sel}' есть плейсхолдеры {sorted(inner - src_inner)}, а в исходнике их нет.",
                        None, 0.8, "plural_inner"))
        for name in set(t_pl) - set(s_pl):
            out.append(ctx.issue(key, "plural_mismatch", "medium",
                f"В переводе есть {{{name}, plural}}, а в исходнике нет.", None, 0.7, "plural_extra"))
    return out


# --------------------------------------------------------------------------
def check_glossary(ctx: Context) -> list[Issue]:
    out = []
    for key, t in ctx.tgt.items():
        s = ctx.src.get(key)
        if not s or not t.strip():
            continue
        vs, vt = visible(s), visible(t)
        seen = set()
        for term in ctx.glossary:
            m = term.ru_re.search(vs)
            if not m:
                continue
            bad = term.avoid_re.search(vt) if term.avoid_re else None
            ok = term.ok_re.search(vt) if term.ok_re else True
            if bad:
                ev = f"«{m.group(0)}» по глоссарию переводим как «{term.target}», а тут «{bad.group(0)}»."
            elif term.strict and not ok:
                ev = f"«{m.group(0)}» по глоссарию переводим как «{term.target}», а в переводе этого слова нет."
            else:
                continue
            if term.comment:
                ev += f" Из глоссария: {term.comment}"
            ident = (term.issue_type, term.ru)
            if ident in seen:
                continue
            seen.add(ident)
            conf = 0.85 if bad else 0.7
            out.append(ctx.issue(key, term.issue_type, term.severity, ev, None, conf, "glossary"))
    return out


# --------------------------------------------------------------------------
def check_length(ctx: Context) -> list[Issue]:
    cands = []
    for key, t in ctx.tgt.items():
        s = ctx.src.get(key)
        if not s or not t:
            continue
        vs, vt = visible(s).strip(), visible(t).strip()
        if not vs or len(vs) > 30 or len(words(vs)) > 4:
            continue
        sa, _ = _icu_args(s); ta, _ = _icu_args(t)
        if sa is not None and ta is not None and {a.name for a in sa} - {a.name for a in ta}:
            continue  # bare placeholder names inflate the length; reported elsewhere
        if _restructured_pair(ctx, key):
            continue
        refs = [len(visible(m[key]).strip()) for _, m in ctx.ref_msgs if m.get(key)]
        base = max([len(vs)] + refs)
        ratio = len(vt) / max(1, len(vs))
        if ratio >= 2.0 and len(vt) - len(vs) >= 10 and len(vt) >= 1.6 * base:
            cands.append((key, vs, vt, ratio, base))
    tails_all = Counter()
    # tails shared by several overflowing strings are a strong signal of padding
    tails = Counter()
    for key, vs, vt, ratio, base in cands:
        w = vt.split()
        for n in range(2, min(6, len(w))):
            tails[" ".join(w[-n:]).lower()] += 1
    out = []
    for key, vs, vt, ratio, base in cands:
        w = vt.split()
        tail = next((" ".join(w[-n:]) for n in range(min(6, len(w) - 1), 1, -1)
                     if tails[" ".join(w[-n:]).lower()] >= 2), None)
        if not tail and ratio < 3.0:
            continue
        hint = bool(UI_KEY_HINT.search(key)) or len(words(vs)) <= 2
        sev = "high" if (ratio >= 3 or tail) else "medium"
        ev = (f"В исходнике {len(vs)} символов, в переводе {len(vt)} (в {ratio:.1f} раза длиннее), "
              f"в других языках максимум {base}. ")
        ev += "Это кнопка или заголовок, места там мало." if hint else "Строка короткая, из интерфейса."
        sug = None
        if tail:
            ev += f" Хвост «{tail}» прилеплен ещё к нескольким таким строкам, похоже на мусор."
            t = ctx.tgt[key]
            idx = t.rfind(tail)
            if idx > 0:
                sug = t[:idx].rstrip()
        out.append(ctx.issue(key, "length_overflow", sev, ev, sug, 0.9 if tail else 0.65, "length"))
    return out


# --------------------------------------------------------------------------
NUMERIC_HINT = re.compile(r"(count|num|amount|price|cost|sum|total|level|lvl|place|bet|min|max|value|time|"
                          r"days|hours|minutes|seconds|percent|points|books|respins|nrg)$|^(x|n|id)$", re.I)


def _restructured_pair(ctx: Context, key: str) -> bool:
    """`...End`/`...Suffix` keys absorb text of their `Start`/`Prefix` sibling
    when the target language needs another word order (ru: 'Купить этот' + 'кейс?')."""
    for a, b in (("End", "Start"), ("Suffix", "Prefix"), ("Part2", "Part1"), ("2", "1")):
        if key.endswith(a):
            sib = key[: -len(a)] + b
            s, t = ctx.src.get(sib), ctx.tgt.get(sib)
            if s and t is not None and len(visible(t).strip()) < 0.6 * len(visible(s).strip()):
                return True
    return False


def check_suffix_harmony(ctx: Context) -> list[Issue]:
    if not ctx.is_kk():
        return []
    out = []
    for key, t in ctx.tgt.items():
        found = list(lang_kk.PLACEHOLDER_AFFIX.finditer(t))
        if not found:
            continue
        parts, low_only = [], True
        for m in found:
            ph, affix = m.group(1), m.group(3)
            name = ph.strip("{}")
            ordinal = affix in lang_kk.ORDINAL_OK
            if not ordinal:
                low_only = False
            parts.append(f"«{m.group(0)}»")
        sev = "low" if low_only else ("medium" if all(
            NUMERIC_HINT.search(m.group(1).strip('{}')) for m in found) else "high")
        ev = ("После плейсхолдера вписано готовое окончание: " + ", ".join(parts) +
              ". Какое окончание нужно, зависит от того, что подставится, заранее его не угадать. "
              "Лучше переписать фразу без окончания.")
        out.append(ctx.issue(key, "suffix_harmony", sev, ev, rephrase_affix(t), 0.9 if sev != "low" else 0.5,
                             "placeholder_affix"))
    return out


_POSTPOSITION_RULES = [
    # dative + сатып алу / сатып ал / айналдыру -> үшін
    (re.compile(r"(\{\w+\}|%s)[-‑']?(?:ға|ге|қа|ке)(\s+(?:сатып ал|айналдыр|аш|сыйла|жөнде))"), r"\1 үшін\2"),
    # dative/ablative + дейін / бастап / кейін
    (re.compile(r"(\{\w+\}|%s)[-‑']?(?:ға|ге|қа|ке)(\s+дейін)"), r"\1\2"),
    (re.compile(r"(\{\w+\}|%s)[-‑']?(?:дан|ден|тан|тен|нан|нен)(\s+бастап)"), r"\1\2"),
    # {x}-нан көп/аз ... болмайды -> limit wording
    (re.compile(r"^(\{\w+\})[-‑']?(?:дан|ден|тан|тен|нан|нен)\s+көп\s+сатып\s+алуға\s+болмайды$"),
     r"Ең көбі \1 сатып алуға болады"),
    (re.compile(r"^(\{\w+\})[-‑']?(?:дан|ден|тан|тен|нан|нен)\s+аз\s+сатып\s+алуға\s+болмайды$"),
     r"Ең азы \1 сатып алуға болады"),
]


def rephrase_affix(text: str) -> str | None:
    """Automatic rewording for common affix-after-placeholder patterns."""
    new = text
    for rx, rep in _POSTPOSITION_RULES:
        new = rx.sub(rep, new)
    if new != text and not lang_kk.PLACEHOLDER_AFFIX.search(new):
        return new
    return None


# --------------------------------------------------------------------------
def _cap(x: str) -> str:
    return x[:1].upper() + x[1:]


def check_orthography(ctx: Context) -> list[Issue]:
    out = []
    kk = ctx.is_kk()
    cyr_target = (ctx.target_lang or "").split("_")[0] in CYRILLIC_LOCALES
    whitelist = OK_WORDS.get((ctx.target_lang or "").split("_")[0], set())
    for key, t in ctx.tgt.items():
        if not t:
            continue
        problems, fixed = [], t
        src_tokens = {x.lower() for x in words(ctx.src.get(key) or "")}
        parts = [p for m in TOKEN.finditer(visible(t)) for p in re.split(r"[-‑]", m.group(0)) if p]
        for w in parts:
            # 1) Latin homoglyphs inside a Cyrillic word (or the other way round)
            if cyr_target and CYR.search(w) and re.search(r"[A-Za-z]", w):
                rep = "".join((("і" if kk and ch == "i" else lang_kk.HOMOGLYPHS.get(ch, ch))
                               if re.match(r"[A-Za-z]", ch) else ch) for ch in w)
                problems.append(f"в слове «{w}» латинские буквы вместо кириллицы, надо «{rep}»")
                fixed = fixed.replace(w, rep)
                continue
            if not CYR.search(w):
                continue
            # 2) lower-case letter inside an all-caps word (САғ)
            letters = [ch for ch in w if ch.isalpha()]
            if len(letters) >= 3 and sum(ch.isupper() for ch in letters) >= len(letters) - 1 \
                    and any(ch.islower() for ch in letters) and letters[0].isupper() and letters[-1].islower() \
                    and sum(ch.isupper() for ch in letters) >= 2:
                problems.append(f"слово капсом, но внутри строчная буква: «{w}» → «{w.upper()}»")
                fixed = fixed.replace(w, w.upper())
                continue
            if not kk:
                continue
            lw = w.lower()
            if lw in whitelist or len(lw) < 4 or ctx.vocab[lw] > 2 or lw in src_tokens:
                continue
            # 3) Russian look-alike instead of a Kazakh letter (сагат -> сағат)
            best = None
            for i, ch in enumerate(lw):
                for rep in lang_kk.LOOKALIKE.get(ch, ""):
                    cand = lw[:i] + rep + lw[i + 1:]
                    c = ctx.vocab[cand]
                    if c >= 3 and c >= 3 * ctx.vocab[lw] and (best is None or c > best[1]):
                        best = (cand, c, ch, rep)
            if best:
                cand = _match_case(w, best[0])
                problems.append(f"«{w}» → «{cand}» (русская «{best[2]}» вместо «{best[3]}», "
                                f"правильный вариант есть в файле {best[1]} раз)")
                fixed = re.sub(rf"(?<![\wЀ-ӿ]){re.escape(w)}(?![\wЀ-ӿ])", cand, fixed)
                continue
            # 4) vowel harmony broken inside a word (мектепта -> мектепте)
            h = _harmony_error(ctx, lw)
            if h:
                cand = _match_case(w, h)
                problems.append(f"не тот ряд гласных (сингармонизм): «{w}» → «{cand}»")
                fixed = re.sub(rf"(?<![\wЀ-ӿ]){re.escape(w)}(?![\wЀ-ӿ])", cand, fixed)
        if problems:
            sev = "high" if any("латинские" in p or "русская" in p for p in problems) else "medium"
            out.append(ctx.issue(key, "orthography", sev, _cap("; ".join(problems)) + ".",
                                 fixed if fixed != t else None, 0.9 if sev == "high" else 0.75, "orthography"))
    return out


def _match_case(src: str, cand: str) -> str:
    if src.isupper():
        return cand.upper()
    if src[:1].isupper():
        return cand[:1].upper() + cand[1:]
    return cand


_FLIP = str.maketrans({"а": "е", "е": "а", "ы": "і", "і": "ы", "ұ": "ү", "ү": "ұ", "о": "ө", "ө": "о",
                       "ғ": "г", "г": "ғ", "қ": "к", "к": "қ"})


def _harmony_error(ctx: Context, w: str) -> str | None:
    """Return the harmonised word if `w` = known stem + suffix chain of the wrong vowel class."""
    for cut in range(len(w) - 1, 2, -1):
        stem, suf = w[:cut], w[cut:]
        if ctx.vocab[stem] < 2 or not 1 <= len(suf) <= 6:
            continue
        core = re.sub(r"(мен|бен|пен)$", "", suf)
        if not core:
            return None
        sc, fc = lang_kk.vowel_class(stem), lang_kk.vowel_class(core)
        if not sc or not fc or sc == fc:
            return None
        if not re.fullmatch(r"(лар|лер|дар|дер|тар|тер|ға|ге|қа|ке|да|де|та|те|дан|ден|тан|тен|нан|нен|"
                            r"ны|ні|ды|ді|ты|ті|ның|нің|дың|дің|тың|тің|ы|і|сы|сі|ын|ін|ымен|імен)+", suf):
            return None
        alt = stem + core.translate(_FLIP) + suf[len(core):]
        native = any(ch in lang_kk.KAZAKH_ONLY for ch in stem)
        if lang_kk.vowel_class(alt[cut:cut + len(core)]) == sc and (native or ctx.vocab[alt] >= 1):
            return alt
        return None
    return None


OK_WORDS = {"kk": set("""бері бөлу ер тең кеше айда бару бұлт жаса келу кеме кайф ок үр орыс алма алды
дала есен минус база елес жарық дағы алса атты отты лотты қалам бізге бізде бізді тері тауып
бірқатар біраз бірақ""".split())}


# --------------------------------------------------------------------------
UZ_MARK = re.compile(r"[ʻʼ‘’]|o‘|g‘|\b(va|uchun|bilan|qilish|bo‘l|ni|lar|xatosi|tanlash|olish|yangi|jami)\b|"
                     r"(lar|lari|larni|ning|dagi)\b", re.I)
PT_ES_MARK = re.compile(r"[ãõçáéíóúêâñ¿¡]|\b(para|o|de|do|da|por|favor|será|novamente|el|la|los|es)\b", re.I)
EN_MARK = re.compile(r"\b(the|to|and|of|is|your|you|with|for|please|equipped|start)\b", re.I)


LOCALE_NAMES = {"uz": "узбекский", "en": "английский", "pt": "португальский", "es": "испанский",
                "tr": "турецкий", "ru": "русский"}


def guess_latin_language(text: str) -> str | None:
    t = visible(text)
    scores = {"узбекский": len(UZ_MARK.findall(t)), "португальский/испанский": len(PT_ES_MARK.findall(t)),
              "английский": len(EN_MARK.findall(t))}
    lang, sc = max(scores.items(), key=lambda x: x[1])
    return lang if sc else None


def check_wrong_language(ctx: Context) -> list[Issue]:
    out = []
    tl = (ctx.target_lang or "").split("_")[0]
    cyr_target = tl in CYRILLIC_LOCALES
    # Latin words the glossary itself prescribes (Battle Pass, Grand Coins, brands)
    gloss_lat = {w.lower() for g in ctx.glossary for w in words(g.target) if LAT.search(w)}
    for key, t in ctx.tgt.items():
        s = ctx.src.get(key)
        if not s or not t.strip() or norm(s) == norm(t) or "@" in key:
            continue
        same_ref = [loc for loc, m in ctx.ref_msgs if m.get(key) and norm(m[key]) == norm(t)
                    and len(norm(t)) >= 4]
        vt = visible(t)
        lat_words = [w for w in words(vt) if LAT.search(w) and not CYR.search(w)]
        src_lat = {w.lower() for w in words(s) if LAT.search(w)}
        foreign = [w for w in lat_words if w.lower() not in src_lat and w.lower() not in gloss_lat and len(w) >= 2]
        cyr_n, lat_n = len(CYR.findall(vt)), len(LAT.findall(vt))
        if cyr_target and foreign and lat_n > cyr_n and CYR.search(visible(s)):
            lang = guess_latin_language(t)
            if same_ref:
                lang = lang or LOCALE_NAMES.get(same_ref[0].split("_")[0], same_ref[0])
            if not lang and not same_ref and (len(foreign) < 3 or CYR.search(vt)):
                continue  # brand names inside a Kazakh phrase
            logo = all(w.isupper() for w in foreign) and not CYR.search(vt) and any(
                loc.startswith("en") for loc in same_ref)
            ev = f"В {tl}-файле текст на латинице" + (f", похоже на {lang}" if lang else "")
            if same_ref:
                ev += f", слово в слово как в {', '.join(same_ref)}"
            ev += f". Слова: {', '.join(foreign[:5])}."
            sev = "low" if logo else ("high" if (len(foreign) >= 2 or same_ref) else "medium")
            if logo:
                ev += " Может быть, это логотип или название, его оставили как в en."
            out.append(ctx.issue(key, "wrong_language", sev, ev, None,
                                 0.4 if logo else (0.95 if same_ref and len(foreign) >= 2 else 0.7), "script_language"))
        elif not cyr_target and CYR.search(vt) and len(CYR.findall(vt)) > len(LAT.findall(vt)):
            out.append(ctx.issue(key, "wrong_language", "high",
                f"В {tl}-файле кириллица, а должна быть латиница.", None, 0.85, "script_language"))
        elif same_ref and not cyr_target and len(words(vt)) >= 3 and guess_latin_language(t) == "английский":
            out.append(ctx.issue(key, "wrong_language", "medium",
                f"Перевод такой же, как в {', '.join(same_ref)}, и похоже, что это просто английский.",
                None, 0.6, "same_as_reference"))
    return out


# --------------------------------------------------------------------------
def check_inconsistent(ctx: Context) -> list[Issue]:
    out = []
    groups = defaultdict(list)
    for key, t in ctx.tgt.items():
        s = ctx.src.get(key)
        if not s or not t.strip() or len(words(s)) > 4:
            continue
        groups[norm(visible(s))].append(key)
    for s_norm, keys in groups.items():
        if len(keys) < 3 or not s_norm:
            continue
        variants = Counter(norm(visible(ctx.tgt[k])) for k in keys)
        if len(variants) < 2:
            continue
        top, top_n = variants.most_common(1)[0]
        if top_n < 2 or len(re.sub(r"\W", "", s_norm)) < 3:
            continue
        terms = [g for g in ctx.glossary if g.ru_re.search(s_norm)]
        for k in keys:
            v = norm(visible(ctx.tgt[k]))
            if v == top or variants[v] > 1:
                continue
            if _stems(v) & _stems(top) and jaccard(_stems(v), _stems(top)) >= 0.5:
                continue  # same words, different inflection
            if terms and all((g.ok_re is None or g.ok_re.search(v)) and not (g.avoid_re and g.avoid_re.search(v))
                             for g in terms):
                continue  # an accepted glossary rendering (сыйлық / сыйақы / жүлде)
            sug = _match_case_phrase(ctx.tgt[k], _restore_case(ctx.src[k], top))
            out.append(ctx.issue(k, "inconsistent_term", "low",
                f"«{ctx.src[k].strip()}» в {top_n} других местах переведено как «{top}», а тут «{v}».",
                sug, 0.55, "same_source_variants"))
    # duplicated keys with conflicting values
    for k, occ in ctx.target.duplicates().items():
        vals = [e.value for e in occ if isinstance(e.value, str)]
        if len({norm(v) for v in vals}) > 1:
            lines = ", ".join(str(e.line) for e in occ)
            iss = ctx.issue(k, "inconsistent_term", "low",
                f"Ключ встречается несколько раз (строки {lines}), и значения разные: " +
                " / ".join(f"«{v}»" for v in vals) + ". Flutter возьмёт последнее.", None, 0.6, "duplicate_key")
            out.append(iss)
    return out


def _stems(text):
    return {w[:5] for w in TOKEN.findall(text)}


def _restore_case(src, variant):
    if src.strip().isupper():
        return variant.upper()
    return variant[:1].upper() + variant[1:] if src.strip()[:1].isupper() else variant


def _match_case_phrase(orig, new):
    return new


# --------------------------------------------------------------------------
NEG_SRC = re.compile(r"(?i)(^|[^а-яё])(не|нет|без|ни|нельзя)([^а-яё]|$)|недоступ|невозмож|неакт")
NEG_KK = re.compile(r"(?i)(емес|жоқ|сыз\b|сіз\b|ма[йсғу]|ме[йсгу]|ба[йсғу]|бе[йсгу]|па[йсғу]|пе[йсгу]|"
                    r"мады|меді|пады|педі|бады|беді|мау|меу|пау|пеу|бау|беу|маған|меген|баған|беген|паған|пеген|"
                    r"қолжетімсіз|жеткіліксіз|тыйым|болмайды|ешқандай)")
DIGITS = re.compile(r"(?<![\d/])\d+(?![\d/])")


def check_mt_suspect(ctx: Context) -> list[Issue]:
    out = []
    kk = ctx.is_kk()
    # a) a translation reused for an unrelated source: the odd one out among keys
    #    that share the same target text, judged by the source AND every reference
    by_t = defaultdict(list)
    for k, t in ctx.tgt.items():
        if len(norm(t)) >= 4 and ctx.src.get(k):
            by_t[norm(t)].append(k)
    langs = [ctx.src] + [m for _, m in ctx.ref_msgs]
    for t_norm, keys in by_t.items():
        if len(keys) < 3 or len(keys) > 12:
            continue
        def sims(a, b):
            return [jaccard(trigrams(m[a]), trigrams(m[b])) for m in langs if m.get(a) and m.get(b)]

        def sim(a, b):
            v = sims(a, b)
            return max(v) if v else 0

        def same_meaning(a, b):
            if norm(ctx.src[a]) == norm(ctx.src[b]):
                return True
            v = sims(a, b)
            return sum(x >= 0.3 for x in v) >= min(2, len(v)) if v else False
        # union-find on "same meaning" (similar in any language)
        parent = {k: k for k in keys}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for a in keys:
            for b in keys:
                if a < b and same_meaning(a, b):
                    parent[find(a)] = find(b)
        clusters = defaultdict(list)
        for k in keys:
            clusters[find(k)].append(k)
        big = [c for c in clusters.values() if len(c) >= 2]
        if len(big) != 1:
            continue
        main = big[0]
        for c in clusters.values():
            if len(c) != 1:
                continue
            k = c[0]
            if max(sim(k, m) for m in main) >= 0.2:
                continue
            ex = main[0]
            ev = (f"Перевод «{ctx.tgt[k]}» такой же, как у {len(main)} ключей с другим смыслом "
                  f"(например {ex}: «{ctx.src[ex]}»), а здесь в исходнике «{ctx.src[k]}». "
                  f"Похоже, перевод подтянули из другого места.")
            out.append(ctx.issue(k, "machine_translation_suspect", "medium", ev, None, 0.65, "reused_translation"))
    # b) numbers changed, c) Russian words left inside the translation
    for k, t in ctx.tgt.items():
        s = ctx.src.get(k)
        if not s or not t.strip() or norm(s) == norm(t):
            continue
        sd = Counter(DIGITS.findall(_join_thousands(visible(s))))
        td = Counter(DIGITS.findall(_join_thousands(visible(t))))
        if sd and (sd - td):
            out.append(ctx.issue(k, "machine_translation_suspect", "high",
                f"Числа не сходятся: в исходнике {sorted(sd.elements())}, в переводе {sorted(td.elements())}.",
                None, 0.8, "numbers"))
        if kk:
            s_tokens = {x.lower() for x in words(s)}
            rus = [w for w in words(t) if CYR.search(w) and not any(c in lang_kk.KAZAKH_ONLY for c in w)
                   and len(w) >= 4 and w.lower() in s_tokens and not ctx.attested(w)
                   and (RU_MORPH.search(w.lower()) or w.lower() in RU_FUNCTION_WORDS)]
            if rus and len(words(t)) > len(rus):
                out.append(ctx.issue(k, "machine_translation_suspect", "medium",
                    f"В казахском тексте остались русские слова: {', '.join(rus)}.", None, 0.7, "russian_words"))
    return out


def _join_thousands(text: str) -> str:
    return re.sub(r"(?<=\d)[.,\s\u00a0](?=\d{3}\b)", "", text)


ALL_CHECKS = [check_untranslated, check_same_as_source, check_placeholders, check_plurals,
              check_glossary, check_length, check_suffix_harmony, check_orthography,
              check_wrong_language, check_inconsistent, check_mt_suspect]


def run_checks(ctx: Context, only: set[str] | None = None) -> list[Issue]:
    issues = []
    for fn in ALL_CHECKS:
        issues.extend(fn(ctx))
    if only:
        issues = [i for i in issues if i.issue_type in only]
    # one issue per (key, type, detector): merge evidence of duplicates
    merged = {}
    for i in issues:
        k = (i.key, i.issue_type, i.detector)
        if k in merged:
            if i.evidence not in merged[k].evidence:
                merged[k].evidence += " " + i.evidence
        else:
            merged[k] = i
    order = {t: n for n, t in enumerate(["high", "medium", "low"])}
    return sorted(merged.values(), key=lambda i: (order[i.severity], i.issue_type, i.line or 0, i.key))
