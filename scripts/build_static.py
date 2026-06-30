#!/usr/bin/env python3
"""Build a single self-contained docs/taste-index.html — no server, no deps.

Bakes every show's data into the page and reimplements similarity, recommendation
(centroid + Rocchio dislike), genre filtering, and axis-profile query in client-side
JS. Reuses the CSS + markup from taste_index.web.PAGE so it matches the served UI.

    python3 scripts/build_static.py     # -> docs/taste-index.html (double-click to open)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from taste_index import cli, db, space, web  # noqa: E402

DB = REPO / "taste_index.db"
OUT = REPO / "docs" / "taste-index.html"

# Client-side reimplementation of the API logic over the embedded DATA blob.
STATIC_JS = r"""
const AXES=DATA.axes, GENRES=DATA.genres, SHOWS=DATA.shows;
const TITLES=Object.keys(SHOWS).sort();
const liked=[], disliked=[];
const $=s=>document.querySelector(s);

const dist=(a,b)=>Math.sqrt(a.reduce((s,v,i)=>s+(v-b[i])**2,0));
const genresOf=t=>(SHOWS[t]?SHOWS[t].genres:[]);
const showsWithGenre=g=>TITLES.filter(t=>genresOf(t).includes(g));
const centroid=ts=>AXES.map((_,i)=>ts.reduce((s,t)=>s+SHOWS[t].values[i],0)/ts.length);
const gbadges=gs=>(gs||[]).map(g=>`<span class="badge">${g}</span>`).join('');
const actBtns=t=>{const e=encodeURIComponent(t);return `<button class="act${liked.includes(t)?' lk-on':''}" data-act="like" data-t="${e}" title="Add to likes">+</button><button class="act${disliked.includes(t)?' lk-on':''}" data-act="dislike" data-t="${e}" title="Add to dislikes">&minus;</button>`;};
function rowItem(title,genres,tail){
  return `<li><span><button class="lk" data-t="${encodeURIComponent(title)}">${title}</button>${gbadges(genres)}</span><span class="racts">${actBtns(title)}${tail||''}</span></li>`;
}

function bars(values){
  return '<div class="axes">'+AXES.map((a,i)=>{const v=values[i];
    return `<div class="ax"><span class="lbl">${a.name}</span><span class="bar"><span style="width:${v*10}%"></span></span><span class="v">${v}</span></div>`;}).join('')+'</div>';
}
function neighborList(items){
  if(!items.length) return '<div class="dist">No matches.</div>';
  return '<ul class="list">'+items.map(it=>rowItem(it.title,it.genres,`<span class="dist">${it.distance}</span>`)).join('')+'</ul>';
}
function nearestTo(vec,n,exclude,allowed){
  return TITLES.filter(t=>!exclude.has(t)&&(!allowed||allowed.has(t)))
    .map(t=>({title:t,distance:+dist(vec,SHOWS[t].values).toFixed(2),genres:genresOf(t)}))
    .sort((a,b)=>a.distance-b.distance).slice(0,n);
}
function loadShow(title){
  if(!SHOWS[title]){ $('#profile').innerHTML='<div class="err">Unknown show.</div>'; return; }
  $('#pick').value=title;
  const s=SHOWS[title];
  let allowed=null;
  if($('#simSameGenre').checked){ allowed=new Set(); genresOf(title).forEach(g=>showsWithGenre(g).forEach(t=>allowed.add(t))); }
  const neighbors=nearestTo(s.values,8,new Set([title]),allowed);
  let html=`<div style="margin:8px 0 2px">${gbadges(s.genres)}</div>`+bars(s.values);
  html+=s.scores.map(x=>`<div class="just"><b>${x.axis} ${x.value}</b> &middot; ${x.justification} <i>(${x.confidence})</i></div>`).join('');
  html+='<h2 style="margin-top:16px">Nearest in taste-space</h2>'+neighborList(neighbors);
  $('#profile').innerHTML=html;
}

const chipHtml=(arr,list)=>arr.map((t,i)=>`<span class="chip">${t}<b data-list="${list}" data-i="${i}">&times;</b></span>`).join('');
function renderChips(){
  $('#chips').innerHTML=chipHtml(liked,'like')||'<span class="dist">No likes yet.</span>';
  $('#dchips').innerHTML=chipHtml(disliked,'dislike');
}
function recommend(){
  const present=liked.filter(t=>SHOWS[t]);
  if(!present.length){ $('#recs').innerHTML='<div class="dist">Add a few shows you like first.</div>'; return; }
  const neg=disliked.filter(t=>SHOWS[t]);
  const cl=centroid(present);
  let target=cl;
  if(neg.length){ const cd=centroid(neg); target=cl.map((v,i)=>Math.min(10,Math.max(0,v+0.5*(v-cd[i])))); }
  const g=$('#recGenre').value;
  const allowed=g?new Set(showsWithGenre(g)):null;
  const recs=nearestTo(target,12,new Set([...liked,...disliked]),allowed);
  let head='Recommended'; if(g) head+=' &middot; '+g; if(neg.length) head+=' &middot; away from '+neg.length+' disliked';
  $('#recs').innerHTML=`<h2 style="margin-top:14px">${head}</h2>`+neighborList(recs);
}

function buildFilters(){
  $('#filters').innerHTML=AXES.map(a=>`<div class="frow" data-axis="${a.id}"><span class="lbl">${a.name}</span><input type="range" min="0" max="10" value="0" data-kind="min"><input type="range" min="0" max="10" value="10" data-kind="max"><span class="frd" id="frd-${a.id}">0&ndash;10</span></div>`).join('');
}
function syncPair(el){
  const row=el.closest('.frow'); const mn=row.querySelector('[data-kind=min]'),mx=row.querySelector('[data-kind=max]');
  if(+mn.value>+mx.value){ if(el.dataset.kind==='min') mx.value=mn.value; else mn.value=mx.value; }
  $('#frd-'+row.dataset.axis).innerHTML=mn.value+'&ndash;'+mx.value;
}
function runQuery(){
  const fs=[...document.querySelectorAll('.frow')].map(r=>({id:+r.dataset.axis,min:+r.querySelector('[data-kind=min]').value,max:+r.querySelector('[data-kind=max]').value})).filter(s=>s.min>0||s.max<10);
  const matches=TITLES.filter(t=>fs.every(s=>{const v=SHOWS[t].values[s.id-1]; return v>=s.min&&v<=s.max;}));
  const shown=matches.slice(0,60);
  const head=`${matches.length} show${matches.length===1?'':'s'} match`+(fs.length?'':' (no filter)');
  let html=`<h2 style="margin-top:14px">${head}</h2><ul class="list">`+shown.map(t=>rowItem(t,genresOf(t),'')).join('')+'</ul>';
  if(matches.length>shown.length) html+=`<div class="dist">showing first ${shown.length}</div>`;
  $('#filterResults').innerHTML=html;
}

function addPref(title,kind){
  const arr=kind==='dislike'?disliked:liked, other=kind==='dislike'?liked:disliked;
  const oi=other.indexOf(title); if(oi>=0) other.splice(oi,1);
  if(!arr.includes(title)) arr.push(title);
  renderChips();
  if($('#pick').value) loadShow($('#pick').value);
  if(liked.length) recommend();
}
document.addEventListener('click',e=>{
  const a=e.target.closest('.act'); if(a){ addPref(decodeURIComponent(a.dataset.t),a.dataset.act); return; }
  const lk=e.target.closest('.lk'); if(lk){ loadShow(decodeURIComponent(lk.dataset.t)); return; }
  const x=e.target.closest('.chip b'); if(x){ (x.dataset.list==='dislike'?disliked:liked).splice(+x.dataset.i,1); renderChips(); if(liked.length&&$('#recs').innerHTML) recommend(); }
});
$('#pick').addEventListener('change',e=>{ if(e.target.value) loadShow(e.target.value); });
$('#simSameGenre').addEventListener('change',()=>{ if($('#pick').value) loadShow($('#pick').value); });
$('#addLike').addEventListener('click',()=>{ const v=$('#likeInput').value.trim(); if(v&&!liked.includes(v)){ liked.push(v); renderChips(); } $('#likeInput').value=''; });
$('#likeInput').addEventListener('keydown',e=>{ if(e.key==='Enter') $('#addLike').click(); });
$('#addDislike').addEventListener('click',()=>{ const v=$('#dislikeInput').value.trim(); if(v&&!disliked.includes(v)){ disliked.push(v); renderChips(); } $('#dislikeInput').value=''; });
$('#dislikeInput').addEventListener('keydown',e=>{ if(e.key==='Enter') $('#addDislike').click(); });
$('#recBtn').addEventListener('click',recommend);
$('#clearBtn').addEventListener('click',()=>{ liked.length=0; disliked.length=0; renderChips(); $('#recs').innerHTML=''; });
$('#filters').addEventListener('input',e=>{ if(e.target.type==='range') syncPair(e.target); });
$('#applyFilter').addEventListener('click',runQuery);
$('#resetFilter').addEventListener('click',()=>{ document.querySelectorAll('.frow').forEach(r=>{ r.querySelector('[data-kind=min]').value=0; r.querySelector('[data-kind=max]').value=10; $('#frd-'+r.dataset.axis).innerHTML='0&ndash;10'; }); $('#filterResults').innerHTML=''; });

$('#shows').innerHTML=TITLES.map(s=>`<option value="${s.replace(/"/g,'&quot;')}">`).join('');
$('#recGenre').innerHTML='<option value="">All genres</option>'+GENRES.map(g=>`<option value="${g}">${g}</option>`).join('');
renderChips(); buildFilters();
"""


def build_data(conn) -> dict:
    meta = web._meta(conn)
    axis_ids = [a["id"] for a in meta["axes"]]
    vecs = space.show_vectors(conn)
    shows = {}
    for t in meta["shows"]:
        s = web._show(conn, t)
        shows[t] = {
            "genres": s["genres"],
            "scores": s["scores"],
            "values": [vecs[t][i] for i in axis_ids],
        }
    return {"axes": meta["axes"], "genres": meta["genres"], "shows": shows}


def ensure_db(conn) -> None:
    db.init_schema(conn)
    if conn.execute("SELECT COUNT(*) FROM show").fetchone()[0]:
        return
    ns = lambda **k: argparse.Namespace(**k)  # noqa: E731
    cli.cmd_init_db(ns(db=str(DB), rubric=str(REPO / "docs/rubric.md")))
    cli.cmd_backfill(ns(db=str(DB), csv=str(REPO / "docs/catalog-scores.csv")))
    cli.cmd_tag_genres(ns(db=str(DB), csv=str(REPO / "docs/genres.csv")))


def main() -> int:
    conn = db.connect(DB)
    ensure_db(conn)
    data = build_data(conn)

    page = web.PAGE
    head = page[: page.index("<script>")]  # everything up to the served JS
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    html = f"{head}<script>\nconst DATA={blob};\n{STATIC_JS}\n</script>\n</body></html>"
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}: {len(data['shows'])} shows, {len(html):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
