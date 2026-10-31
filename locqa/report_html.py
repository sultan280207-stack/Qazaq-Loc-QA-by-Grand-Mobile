"""Self-contained HTML report (no external resources).

Each finding is shown like a proofreader's mark-up: the current translation with
the wrong part struck out and the suggested text written in, plus a plain
explanation of what is wrong.
"""
from __future__ import annotations

import html
import json
from collections import Counter

from .issues import ISSUE_TYPES

TYPE_RU = {
    "untranslated": "Нет перевода",
    "same_as_source": "Оставлен русский текст",
    "placeholder_mismatch": "Сломаны плейсхолдеры",
    "plural_mismatch": "Множественное число (ICU)",
    "glossary_violation": "Не по глоссарию",
    "length_overflow": "Слишком длинно",
    "machine_translation_suspect": "Калька, машинный перевод",
    "inconsistent_term": "Разнобой в терминах",
    "suffix_harmony": "Окончание после плейсхолдера",
    "orthography": "Орфография",
    "wrong_language": "Не тот язык",
}
SEV_RU = {"high": "серьёзно", "medium": "заметно", "low": "мелочь"}


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def render(issues: list[dict], meta: dict) -> str:
    by_type = Counter(i["issue_type"] for i in issues)
    by_sev = Counter(i["severity"] for i in issues)
    n, keys = len(issues), len({i["key"] for i in issues})
    reviewed = sum(1 for i in issues if i.get("reviewed_by_human"))
    m = {k: html.escape(str(v)) for k, v in meta.items()}
    data = json.dumps(issues, ensure_ascii=False).replace("</", "<\\/")
    names = json.dumps({**TYPE_RU, **{f"sev:{k}": v for k, v in SEV_RU.items()}}, ensure_ascii=False)

    chips = [f'<button type="button" class="chip on" data-t="">Все <b>{n}</b></button>']
    for t in sorted(ISSUE_TYPES, key=lambda t: -by_type.get(t, 0)):
        if by_type.get(t):
            chips.append(f'<button type="button" class="chip" data-t="{t}" title="{t}">{TYPE_RU[t]} <b>{by_type[t]}</b></button>')

    refs = m.get("refs", "—")
    against = f", сверяли с {refs}" if refs and refs != "—" else ""
    gloss = m.get("glossary", "—")
    gloss_txt = f", глоссарий {gloss}" if gloss and gloss != "—" else ""
    review = m.get("review", "—")
    review_txt = f" Вердикты ревью взяты из {review}." if review and review != "—" else ""
    if reviewed == 0:
        human = "Носитель языка эти находки пока не проверял."
    elif reviewed == n:
        human = "Все находки проверил носитель языка."
    else:
        human = f"Носитель языка проверил {reviewed} из {n}."

    summary = (f"Нашли {n} {_plural(n, 'проблему', 'проблемы', 'проблем')} в {keys} "
               f"{_plural(keys, 'ключе', 'ключах', 'ключах')}: серьёзных {by_sev.get('high', 0)}, "
               f"заметных {by_sev.get('medium', 0)}, мелких {by_sev.get('low', 0)}. {human}")

    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Проверка {m.get('target', '')}</title>
<style>
:root{{--paper:#f7f8fa;--sheet:#fff;--ink:#1d2433;--soft:#667085;--rule:#e3e6eb;
--red:#c8312b;--blue:#1f5fbf;--amber:#9a5b00;--tint:#eef3fb}}
@media (prefers-color-scheme:dark){{:root{{--paper:#15181e;--sheet:#1b1f27;--ink:#e6e8ec;--soft:#9aa3b2;
--rule:#2c323d;--red:#ff7a70;--blue:#86b6ff;--amber:#f0b45a;--tint:#1f2a3a}}}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--paper);color:var(--ink);
font:15px/1.5 "Segoe UI","PT Sans",Roboto,"Noto Sans",system-ui,sans-serif}}
.page{{max-width:1080px;margin:0 auto;padding:28px 16px 64px}}
h1{{font-size:26px;line-height:1.2;font-weight:650;margin:0 0 10px;letter-spacing:-.01em}}
.lead{{max-width:68ch;margin:0 0 6px;font-size:16px}}
.files{{max-width:68ch;margin:0;color:var(--soft);font-size:13px}}
.files code{{color:var(--ink)}}
.tools{{position:sticky;top:0;z-index:2;background:var(--paper);padding:14px 0 10px;margin-top:18px;
border-bottom:1px solid var(--rule)}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chip{{font:inherit;font-size:13px;border:1px solid var(--rule);background:var(--sheet);color:var(--ink);
border-radius:999px;padding:4px 11px;cursor:pointer}}
.chip b{{font-weight:600;color:var(--soft);margin-left:2px;font-variant-numeric:tabular-nums}}
.chip.on{{background:var(--ink);color:var(--paper);border-color:var(--ink)}}
.chip.on b{{color:inherit;opacity:.75}}
.row2{{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}}
.row2 select,.row2 input{{font:inherit;font-size:14px;padding:6px 9px;border:1px solid var(--rule);
border-radius:6px;background:var(--sheet);color:var(--ink)}}
.row2 input{{flex:1 1 220px;min-width:0}}
.count{{color:var(--soft);font-size:13px;margin-left:auto}}
:focus-visible{{outline:2px solid var(--blue);outline-offset:2px}}
.list{{margin:0;padding:0;list-style:none}}
.item{{display:grid;grid-template-columns:220px 1fr;gap:4px 24px;padding:16px 0;border-bottom:1px solid var(--rule)}}
.meta{{font-size:13px;color:var(--soft);min-width:0}}
.key{{font:13px/1.35 ui-monospace,"Cascadia Mono",Consolas,monospace;color:var(--ink);word-break:break-all}}
.sev{{font-weight:600}}
.sev.high{{color:var(--red)}} .sev.medium{{color:var(--amber)}} .sev.low{{color:var(--soft)}}
.body{{min-width:0}}
.src{{color:var(--soft);margin:0 0 4px;white-space:pre-wrap;word-break:break-word}}
.src span{{font-size:12px;margin-right:6px}}
.txt{{margin:0 0 8px;font-size:16px;white-space:pre-wrap;word-break:break-word}}
del{{color:var(--red);text-decoration:line-through;text-decoration-thickness:1.5px}}
ins{{color:var(--blue);text-decoration:none;background:var(--tint);border-bottom:1.5px solid var(--blue)}}
del+ins{{margin-left:3px}}
.none{{color:var(--soft);font-style:italic}}
.why{{margin:0;max-width:75ch;font-size:14px}}
.empty{{padding:40px 0;color:var(--soft)}}
@media (max-width:720px){{.item{{grid-template-columns:1fr}} .meta{{display:flex;flex-wrap:wrap;gap:2px 10px}}
.meta .key{{flex-basis:100%}} h1{{font-size:22px}}}}
@media print{{.tools{{display:none}} body{{background:#fff}} .item{{break-inside:avoid}}}}
</style></head><body><div class="page">
<h1>Проверка перевода {m.get('target', '')}</h1>
<p class="lead">{summary}</p>
<p class="files">Исходник <code>{m.get('source', '')}</code>{against}{gloss_txt}.{review_txt}
Отчёт собран {m.get("generated", "")}, locqa {m.get('version', '')}. Зачёркнутое красным предлагаем убрать,
синим вписано, что поставить вместо.</p>
<div class="tools">
<div class="chips" id="chips">{''.join(chips)}</div>
<div class="row2">
<select id="sev" aria-label="Важность"><option value="">Любая важность</option>
<option value="high">Только серьёзные</option><option value="medium">Только заметные</option><option value="low">Только мелочи</option></select>
<input id="q" type="search" placeholder="Искать по ключу или тексту" aria-label="Поиск">
<span class="count" id="cnt"></span>
</div></div>
<ol class="list" id="list"></ol>
</div>
<script>
const D={data};
const N={names};
const list=document.getElementById('list'),sevSel=document.getElementById('sev'),q=document.getElementById('q'),cnt=document.getElementById('cnt');
let type='';
function esc(s){{return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function tok(s){{return (s||'').split(/(\\s+|[.,:;!?«»()"])/).filter(x=>x)}}
function diff(a,b){{
  const x=tok(a),y=tok(b),n=x.length,m=y.length;
  if(n*m>250000)return '<del>'+esc(a)+'</del> <ins>'+esc(b)+'</ins>';
  const L=Array.from({{length:n+1}},()=>new Uint16Array(m+1));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)L[i][j]=x[i]===y[j]?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
  const out=[];let i=0,j=0;
  const push=(k,s)=>{{const p=out[out.length-1];if(p&&p[0]===k)p[1]+=s;else out.push([k,s])}};
  while(i<n&&j<m){{if(x[i]===y[j]){{push('=',x[i]);i++;j++}}else if(L[i+1][j]>=L[i][j+1]){{push('-',x[i]);i++}}else{{push('+',y[j]);j++}}}}
  while(i<n)push('-',x[i++]);while(j<m)push('+',y[j++]);
  const word=t=>/[^\\s.,:;!?«»()"]/.test(t);
  const same=out.filter(o=>o[0]==='=').reduce((s,o)=>s+tok(o[1]).filter(word).length,0);
  const total=y.filter(word).length;
  if(total>=2&&same/total<0.4)return '<del>'+esc(a)+'</del> <ins>'+esc(b)+'</ins>';
  return out.map(([k,s])=>k==='='?esc(s):k==='-'?'<del>'+esc(s)+'</del>':'<ins>'+esc(s)+'</ins>').join('');
}}
function origin(o){{return o==='review'?'добавлено при ревью':o==='auto+review'?'нашёл инструмент, ревью подтвердило':'нашёл инструмент'}}
function card(i){{
  let t;
  if(i.target==null&&i.suggestion)t='<ins>'+esc(i.suggestion)+'</ins>';
  else if(i.target==null)t='<span class="none">строки нет</span>';
  else if(i.suggestion&&i.suggestion!==i.target)t=diff(i.target,i.suggestion);
  else t=esc(i.target);
  const where=i.line?'строка '+i.line:'в файле нет';
  const human=i.reviewed_by_human?'<div>проверил носитель</div>':'';
  return `<li class="item"><div class="meta"><div class="key">${{esc(i.key)}}</div>
<div><span class="sev ${{i.severity}}">${{N['sev:'+i.severity]}}</span>, ${{esc(N[i.issue_type]||i.issue_type).toLowerCase()}}</div>
<div>${{where}}, уверенность ${{Math.round((i.confidence||0)*100)}}%</div><div>${{origin(i.origin)}}</div>${{human}}</div>
<div class="body"><p class="src"><span>ru</span>${{esc(i.source)||'<span class="none">нет в исходнике</span>'}}</p>
<p class="txt">${{t}}</p><p class="why">${{esc(i.evidence)}}</p></div></li>`;
}}
function draw(){{
  const s=sevSel.value,w=q.value.trim().toLowerCase();let h='',k=0;
  for(const i of D){{
    if(type&&i.issue_type!==type)continue;if(s&&i.severity!==s)continue;
    if(w&&!(i.key+' '+(i.source||'')+' '+(i.target||'')+' '+(i.suggestion||'')+' '+i.evidence).toLowerCase().includes(w))continue;
    k++;h+=card(i);
  }}
  list.innerHTML=h||'<li class="empty">Под такие условия ничего не подходит. Сбросьте фильтр или поиск.</li>';
  cnt.textContent='Показано '+k+' из '+D.length;
}}
document.getElementById('chips').addEventListener('click',e=>{{
  const b=e.target.closest('.chip');if(!b)return;type=b.dataset.t;
  for(const c of document.querySelectorAll('.chip'))c.classList.toggle('on',c===b);draw();
}});
sevSel.onchange=draw;q.oninput=draw;draw();
</script></body></html>"""
