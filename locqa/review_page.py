"""Offline review page for a native speaker.

`locqa review-page --report report.json --out review.html` writes one HTML file with
the findings grouped by key. The reviewer marks each change as right or not needed,
can rewrite the suggested text, and downloads a CSV in the `--review` format.
Nothing is sent anywhere: marks live in the browser's localStorage only.
"""
from __future__ import annotations

import html
import json

from .report_html import TYPE_RU


def render_review_page(issues: list[dict], name: str = "") -> str:
    groups: dict[str, dict] = {}
    for i in issues:
        g = groups.setdefault(i["key"], {"key": i["key"], "line": i.get("line"), "source": i.get("source"),
                                         "target": i.get("target"), "suggestion": None, "items": []})
        if i.get("suggestion") and not g["suggestion"]:
            g["suggestion"] = i["suggestion"]
        g["items"].append({"t": i["issue_type"], "sev": i["severity"], "ev": i.get("evidence", ""),
                           "sug": i.get("suggestion") or ""})
    data = json.dumps(list(groups.values()), ensure_ascii=False).replace("</", "<\\/")
    names = json.dumps(TYPE_RU, ensure_ascii=False)
    title = html.escape(name or "перевода")
    store = json.dumps("locqa-review:" + (name or "") + ":" + str(len(issues)))
    n = len(groups)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Проверка правок {title}</title>
<style>
:root{{--paper:#f7f8fa;--sheet:#fff;--ink:#1d2433;--soft:#667085;--rule:#e3e6eb;
--red:#c8312b;--blue:#1f5fbf;--green:#1e7a46;--tint:#eef3fb;--warn:#9a5b00}}
@media (prefers-color-scheme:dark){{:root{{--paper:#15181e;--sheet:#1b1f27;--ink:#e6e8ec;--soft:#9aa3b2;
--rule:#2c323d;--red:#ff7a70;--blue:#86b6ff;--green:#6fd39b;--tint:#1f2a3a;--warn:#f0b45a}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 "Segoe UI","PT Sans",Roboto,"Noto Sans",system-ui,sans-serif}}
.page{{max-width:900px;margin:0 auto;padding:28px 16px 80px}}
h1{{font-size:26px;line-height:1.2;font-weight:650;margin:0 0 10px}}
.lead{{max-width:68ch;margin:0 0 8px}}
.who{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0 0}}
input,textarea,select,button{{font:inherit;color:var(--ink)}}
input,textarea,select{{border:1px solid var(--rule);border-radius:6px;background:var(--sheet);padding:6px 9px}}
.bar{{position:sticky;top:0;z-index:2;background:var(--paper);border-bottom:1px solid var(--rule);
padding:12px 0;margin-top:16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
.bar input{{flex:1 1 180px;min-width:0}}
.prog{{font-variant-numeric:tabular-nums}}
.btn{{border:1px solid var(--rule);background:var(--sheet);border-radius:6px;padding:6px 12px;cursor:pointer}}
.btn.main{{background:var(--ink);color:var(--paper);border-color:var(--ink)}}
.btn.ok.on{{background:var(--green);border-color:var(--green);color:#fff}}
.btn.no.on{{background:var(--red);border-color:var(--red);color:#fff}}
:focus-visible{{outline:2px solid var(--blue);outline-offset:2px}}
.item{{padding:18px 0;border-bottom:1px solid var(--rule)}}
.head{{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;font-size:13px;color:var(--soft)}}
.key{{font:13px ui-monospace,"Cascadia Mono",Consolas,monospace;color:var(--ink)}}
.state{{margin-left:auto;font-weight:600}}
.state.ok{{color:var(--green)}} .state.no{{color:var(--red)}}
.lbl{{font-size:12px;color:var(--soft);margin:10px 0 2px}}
.ru,.cur{{margin:0;white-space:pre-wrap;word-break:break-word}}
.cur{{font-size:16px}}
.none{{color:var(--soft);font-style:italic}}
del{{color:var(--red);text-decoration:line-through;text-decoration-thickness:1.5px}}
textarea{{width:100%;min-height:2.6em;font-size:16px;line-height:1.45;resize:vertical}}
.warn{{color:var(--warn);font-size:13px;margin:4px 0 0}}
.why{{margin:8px 0 0;padding-left:18px;font-size:14px;max-width:75ch}}
.why b{{font-weight:600}}
.row{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}}
.row input{{flex:1 1 220px;min-width:0}}
.hide{{display:none}}
.msg{{color:var(--soft);font-size:13px}}
</style></head><body><div class="page">
<h1>Проверка правок {title}</h1>
<p class="lead">Здесь {n} строк, которые мы предлагаем поменять. По каждой посмотрите русский текст и наш вариант.
Если вариант правильный, нажмите «Верно». Если ошибки на самом деле нет и строку трогать не надо, нажмите «Не нужно».
Если вариант почти правильный, поправьте текст в поле и нажмите «Верно».</p>
<p class="lead">Отметки сохраняются в этом браузере, страницу можно закрыть и вернуться позже. Когда закончите
(можно и не всё), нажмите «Скачать результат» и отправьте файл команде.</p>
<div class="who"><label for="name">Ваше имя</label><input id="name" autocomplete="name" placeholder="Например, Айгерім Сейітова"></div>
<div class="bar">
<span class="prog" id="prog"></span>
<select id="flt" aria-label="Показать"><option value="">Все строки</option><option value="todo">Ещё не проверенные</option>
<option value="ok">Отмеченные «Верно»</option><option value="no">Отмеченные «Не нужно»</option></select>
<input id="q" type="search" placeholder="Искать по ключу или тексту" aria-label="Поиск">
<button class="btn main" id="dl" type="button">Скачать результат</button>
<span class="msg" id="msg"></span>
</div>
<div id="list"></div>
</div>
<script>
const G={data};
const N={names};
const KEY={store};
let S={{}};
try{{S=JSON.parse(localStorage.getItem(KEY)||'{{}}')||{{}}}}catch(e){{S={{}}}}
function save(){{try{{localStorage.setItem(KEY,JSON.stringify(S))}}catch(e){{}}}}
const $=id=>document.getElementById(id);
function esc(s){{return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function marks(s){{const out=[];(s||'').replace(/\\{{\\s*([A-Za-z_]\\w*)/g,(m,a)=>out.push('{{'+a+'}}'));
(s||'').replace(/%(\\d+\\$)?[sd]/g,m=>out.push(m));(s||'').replace(/<\\/?\\w+>/g,m=>out.push(m));return out.sort().join(' ')}}
function check(g,text){{const a=marks(g.source),b=marks(text);
if(a===b)return '';return 'Плейсхолдеры или теги не совпадают с русским текстом. В русском: '+(a||'нет')+'. В вашем варианте: '+(b||'нет')+'.'}}
try{{$('name').value=S.__name||''}}catch(e){{}}
$('name').oninput=e=>{{S.__name=e.target.value;save();$('msg').textContent=''}};
function tok(s){{return (s||'').split(/(\\s+|[.,:;!?«»()"])/).filter(x=>x)}}
function marked(a,b){{
  const x=tok(a),y=tok(b),n=x.length,m=y.length;if(!b||a===b||n*m>250000)return esc(a);
  const L=Array.from({{length:n+1}},()=>new Uint16Array(m+1));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)L[i][j]=x[i]===y[j]?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
  let i=0,j=0,h='';
  while(i<n){{if(j<m&&x[i]===y[j]){{h+=esc(x[i]);i++;j++}}else if(j>=m||L[i+1][j]>=L[i][j+1]){{h+=/^\\s+$/.test(x[i])?esc(x[i]):'<del>'+esc(x[i])+'</del>';i++}}else j++}}
  return h;
}}
function view(g,i){{
  const st=S[g.key]||{{}};
  const text=st.text!=null?st.text:(g.suggestion||g.target||'');
  const state=st.v==='ok'?'<span class="state ok">Верно</span>':st.v==='no'?'<span class="state no">Не нужно</span>':'<span class="state">не проверено</span>';
  const why=g.items.map(x=>'<li><b>'+esc(N[x.t]||x.t)+'.</b> '+esc(x.ev)+'</li>').join('');
  const w=check(g,text);
  return `<div class="item" data-i="${{i}}"><div class="head"><span class="key">${{esc(g.key)}}</span><span>${{g.line?'строка '+g.line:'строки нет в файле'}}</span>${{state}}</div>
<div class="lbl">Русский</div><p class="ru">${{esc(g.source)||'<span class="none">нет</span>'}}</p>
<div class="lbl">Сейчас в файле (красным то, что меняем)</div><p class="cur">${{g.target==null?'<span class="none">строки нет</span>':marked(g.target,g.suggestion)}}</p>
<div class="lbl">${{g.suggestion?'Наш вариант (можно исправить)':'Своего варианта у нас нет, можно вписать'}}</div>
<textarea rows="${{Math.min(8,Math.max(1,Math.ceil(text.length/60)+(text.match(/\\n/g)||[]).length))}}" data-k="text">${{esc(text)}}</textarea>
<p class="warn ${{w?'':'hide'}}">${{esc(w)}}</p>
<ul class="why">${{why}}</ul>
<div class="row"><button type="button" class="btn ok ${{st.v==='ok'?'on':''}}" data-v="ok">Верно</button>
<button type="button" class="btn no ${{st.v==='no'?'on':''}}" data-v="no">Не нужно</button>
<input data-k="note" placeholder="Комментарий, если нужен" value="${{esc(st.note||'')}}"></div></div>`;
}}
function progress(){{const d=G.filter(g=>S[g.key]&&S[g.key].v).length;$('prog').textContent='Проверено '+d+' из '+G.length}}
function draw(){{
  const f=$('flt').value,w=$('q').value.trim().toLowerCase();let h='';
  G.forEach((g,i)=>{{const v=(S[g.key]||{{}}).v;
    if(f==='todo'&&v)return;if(f==='ok'&&v!=='ok')return;if(f==='no'&&v!=='no')return;
    if(w&&!(g.key+' '+(g.source||'')+' '+(g.target||'')+' '+(g.suggestion||'')).toLowerCase().includes(w))return;
    h+=view(g,i)}});
  $('list').innerHTML=h||'<p class="msg">Под фильтр ничего не подходит.</p>';progress();
}}
$('list').addEventListener('click',e=>{{const b=e.target.closest('button[data-v]');if(!b)return;
  const it=b.closest('.item'),g=G[+it.dataset.i],st=S[g.key]=S[g.key]||{{}};
  st.v=st.v===b.dataset.v?undefined:b.dataset.v;st.text=it.querySelector('textarea').value;save();
  const y=it.getBoundingClientRect().top;it.outerHTML=view(g,+it.dataset.i);progress();
  const n=$('list').querySelector('.item[data-i="'+it.dataset.i+'"]');if(n)window.scrollBy(0,n.getBoundingClientRect().top-y);
}});
$('list').addEventListener('input',e=>{{const k=e.target.dataset.k;if(!k)return;
  const it=e.target.closest('.item'),g=G[+it.dataset.i],st=S[g.key]=S[g.key]||{{}};st[k]=e.target.value;save();
  if(k==='text'){{const w=check(g,e.target.value),p=it.querySelector('.warn');p.textContent=w;p.classList.toggle('hide',!w)}}
}});
$('flt').onchange=draw;$('q').oninput=draw;
function cell(s){{return '"'+String(s==null?'':s).replace(/"/g,'""')+'"'}}
$('dl').onclick=()=>{{
  const who=$('name').value.trim();
  if(!who){{$('msg').textContent='Сначала впишите своё имя вверху.';$('name').focus();return}}
  const rows=[['key','issue_type','verdict','severity','suggestion','evidence','reviewed_by_human','reviewer','note']];
  let n=0;
  for(const g of G){{const st=S[g.key];if(!st||!st.v)continue;n++;
    const text=(st.text!=null?st.text:(g.suggestion||'')).trim();
    const sug=st.v==='ok'&&text&&text!==(g.target||'')?text:'';
    for(const x of g.items)rows.push([g.key,x.t,st.v==='ok'?'confirm':'reject',x.sev,st.v==='ok'?sug:'',x.ev,'true',who,st.note||'']);
  }}
  if(!n){{$('msg').textContent='Пока ни одна строка не отмечена.';return}}
  const blob=new Blob(['\\ufeff'+rows.map(r=>r.map(cell).join(',')).join('\\r\\n')+'\\r\\n'],{{type:'text/csv;charset=utf-8'}});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='native_review.csv';
  document.body.appendChild(a);a.click();a.remove();
  $('msg').textContent='Файл native_review.csv скачан. Отмечено строк: '+n+'.';
}};
draw();
</script></body></html>"""
