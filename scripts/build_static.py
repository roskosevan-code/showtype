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
const RX=[['loved','❤'],['liked','👍'],['fine','😐'],['nope','👎']];
const WATCH=[['watchlist','🔖','Watchlist'],['seen','👁','Seen'],['dropped','🚪','Bounced']];
const COMPLAINTS=[['slow','Too slow',{1:1}],['dense','Hard to follow',{7:-1}],['cold',"Couldn't connect",{4:1}],['tryhard','Too try-hard',{5:-1}],['unreal',"Didn't buy it",{6:1}],['corny','Too corny',{8:-1,6:1}]];
const PUSH_STEP=1.5, PUSH_CAP=3;
let reactions=JSON.parse(localStorage.getItem('ti-reactions')||'{}');
let watch=JSON.parse(localStorage.getItem('ti-watch')||'{}');
let reasons=JSON.parse(localStorage.getItem('ti-reasons')||'{}');
const saveReactions=()=>localStorage.setItem('ti-reactions',JSON.stringify(reactions));
const saveWatch=()=>localStorage.setItem('ti-watch',JSON.stringify(watch));
const saveReasons=()=>localStorage.setItem('ti-reasons',JSON.stringify(reasons));
const $=s=>document.querySelector(s);

const dist=(a,b)=>Math.sqrt(a.reduce((s,v,i)=>s+(v-b[i])**2,0));
const genresOf=t=>(SHOWS[t]?SHOWS[t].genres:[]);
const showsWithGenre=g=>TITLES.filter(t=>genresOf(t).includes(g));
const centroid=ts=>AXES.map((_,i)=>ts.reduce((s,t)=>s+SHOWS[t].values[i],0)/ts.length);
const gbadges=gs=>(gs||[]).map(g=>`<span class="badge">${g}</span>`).join('');
const qbadge=q=>(q!=null)?`<span class="qb" title="Execution score">Q${q}</span>`:'';
const rxBtns=t=>{const e=encodeURIComponent(t),cur=reactions[t];return '<span class="rx">'+RX.map(([r,em])=>`<button class="rxb${cur===r?' on':''}" data-rx="${r}" data-t="${e}" title="${r}">${em}</button>`).join('')+'</span>';};
const wxBtns=t=>{const e=encodeURIComponent(t),cur=watch[t];return '<span class="wx">'+WATCH.map(([w,em,lbl])=>`<button class="wxb${cur===w?' on':''}" data-wx="${w}" data-t="${e}" title="${lbl}">${em}</button>`).join('')+'</span>';};
function whyText(v,ref){
  const d=AXES.map((a,i)=>({n:a.name,gap:Math.abs(v[i]-ref[i]),v:v[i],r:Math.round(ref[i])}));
  const near=d.slice().sort((a,b)=>a.gap-b.gap).slice(0,3).map(x=>x.n);
  const far=d.slice().sort((a,b)=>b.gap-a.gap)[0];
  let s='Aligns on <b>'+near.join('</b>, <b>')+'</b>';
  if(far.gap>=3) s+=' &middot; differs on <b>'+far.n+'</b> ('+far.v+' vs ~'+far.r+')';
  return s;
}
function rowItem(title,genres,quality,tail,why){
  const e=encodeURIComponent(title);
  return `<li><div class="nrow"><span><button class="lk" data-t="${e}">${title}</button>${gbadges(genres)}${qbadge(quality)}</span><span class="racts">${rxBtns(title)}${wxBtns(title)}${why?'<button class="act why-t" title="Why?">?</button>':''}${tail||''}</span></div>${why?`<div class="why" hidden>${why}</div>`:''}</li>`;
}

function bars(values){
  return '<div class="axes">'+AXES.map((a,i)=>{const v=values[i];
    return `<div class="ax"><span class="lbl">${a.name}</span><span class="bar"><span style="width:${v*10}%"></span></span><span class="v">${v}</span></div>`;}).join('')+'</div>';
}
function neighborList(items,ref){
  if(!items.length) return '<div class="dist">No matches.</div>';
  return '<ul class="list">'+items.map(it=>rowItem(it.title,it.genres,it.quality,`<span class="dist">${it.distance}</span>`, ref?whyText(it.values,ref):'')).join('')+'</ul>';
}
function nearestTo(vec,n,exclude,allowed){
  return TITLES.filter(t=>!exclude.has(t)&&(!allowed||allowed.has(t)))
    .map(t=>({title:t,distance:+dist(vec,SHOWS[t].values).toFixed(2),genres:genresOf(t),quality:SHOWS[t].quality,values:SHOWS[t].values}))
    .sort((a,b)=>a.distance-b.distance).slice(0,n);
}
function loadShow(title){
  if(!SHOWS[title]){ $('#profile').innerHTML='<div class="err">Unknown show.</div>'; return; }
  $('#pick').value=title;
  const s=SHOWS[title];
  let allowed=null;
  if($('#simSameGenre').checked){ allowed=new Set(); genresOf(title).forEach(g=>showsWithGenre(g).forEach(t=>allowed.add(t))); }
  const neighbors=nearestTo(s.values,8,new Set([title]),allowed);
  let html=`<div style="margin:8px 0 2px">${gbadges(s.genres)}${qbadge(s.quality)} ${rxBtns(title)}${wxBtns(title)}</div>`;
  if(s.summary) html+=`<div class="summary">${s.summary}</div>`;
  const meta=[]; if(s.episodes) meta.push('&approx;'+s.episodes+' episodes'); if(s.seasons) meta.push(s.seasons+' season'+(s.seasons===1?'':'s'));
  if(meta.length) html+=`<div class="metaline">${meta.join(' &middot; ')}</div>`;
  html+=bars(s.values);
  html+=s.scores.map(x=>`<div class="just"><b>${x.axis} ${x.value}</b> &middot; ${x.justification} <i>(${x.confidence})</i></div>`).join('');
  if(s.quality!=null) html+=`<div class="qblock"><b>Execution ${s.quality}/10</b> &middot; ${s.quality_reason||''}</div>`;
  html+='<h2 style="margin-top:16px">Nearest in taste-space</h2>'+neighborList(neighbors,s.values);
  $('#profile').innerHTML=html;
}

function setReaction(t,r){
  if(reactions[t]===r) delete reactions[t]; else reactions[t]=r;
  saveReactions(); renderChips();
  if($('#pick').value) loadShow($('#pick').value);
  if($('#recs').innerHTML) recommend();
}
function setWatch(t,w){
  if(watch[t]===w) delete watch[t]; else watch[t]=w;
  saveWatch(); renderChips();
  if($('#pick').value) loadShow($('#pick').value);
  if($('#recs').innerHTML) recommend();
}
function complaintRow(t){
  const e=encodeURIComponent(t), cur=reasons[t]||[];
  return `<div class="rsn" data-t="${e}">`+COMPLAINTS.map(([k,lbl])=>`<button class="rsnb${cur.includes(k)?' on':''}" data-rsn="${k}" data-t="${e}">${lbl}</button>`).join('')+'</div>';
}
function renderChips(){
  const ts=Object.keys(reactions);
  const wl=Object.keys(watch).filter(t=>watch[t]==='watchlist');
  const head=wl.length?`<div class="hint" style="margin:0 0 8px">&#128278; ${wl.length} on your watchlist</div>`:'';
  if(!ts.length){ $('#chips').innerHTML=head+'<span class="dist">No reactions yet — use the &#10084;&#128077;&#128528;&#128078; on any show.</span>'; return; }
  const ord={loved:0,liked:1,fine:2,nope:3}, em=r=>RX.find(x=>x[0]===r)[1];
  ts.sort((a,b)=>(ord[reactions[a]]-ord[reactions[b]])||a.localeCompare(b));
  $('#chips').innerHTML=head+ts.map(t=>{
    const e=encodeURIComponent(t);
    let s=`<span class="chip">${em(reactions[t])} ${t}`;
    if(reactions[t]==='nope'){ const n=(reasons[t]||[]).length; s+=`<b class="rsn-t" data-rt="${e}" title="Why it didn't land">${n?'why&middot;'+n:'why'}</b>`; }
    s+=`<b data-rm="${e}">&times;</b></span>`;
    if(reactions[t]==='nope') s+=complaintRow(t);
    return s;
  }).join('');
}
function collectPushes(){
  const push={};
  const add=t=>(reasons[t]||[]).forEach(k=>{ const c=COMPLAINTS.find(x=>x[0]===k); if(c) for(const a in c[2]) push[a]=(push[a]||0)+c[2][a]*PUSH_STEP; });
  for(const t in reactions) if(reactions[t]==='nope'&&(reasons[t]||[]).length) add(t);
  for(const t in watch) if(watch[t]==='dropped'&&reactions[t]!=='nope'&&(reasons[t]||[]).length) add(t);
  for(const a in push) push[a]=Math.max(-PUSH_CAP,Math.min(PUSH_CAP,push[a]));
  return push;
}
function recommend(){
  const W={loved:2,liked:1,fine:0.4};
  const pos=[], neg=[];
  for(const t in reactions){ if(!SHOWS[t]) continue; if(reactions[t]==='nope'){ if(!(reasons[t]||[]).length) neg.push(t); } else pos.push([t,W[reactions[t]]]); }
  if(!pos.length){ $('#recs').innerHTML='<div class="dist">React to a few shows you liked first (&#10084; or &#128077;).</div>'; return; }
  const wlOnly=$('#wlOnly').checked;
  if(wlOnly && !Object.keys(watch).some(t=>watch[t]==='watchlist')){ $('#recs').innerHTML='<div class="dist">Nothing on your watchlist yet — mark shows with &#128278;.</div>'; return; }
  const wsum=pos.reduce((s,[,w])=>s+w,0);
  const cl=AXES.map((_,i)=>pos.reduce((s,[t,w])=>s+w*SHOWS[t].values[i],0)/wsum);
  let target=cl.slice();
  if(neg.length){ const cd=AXES.map((_,i)=>neg.reduce((s,t)=>s+SHOWS[t].values[i],0)/neg.length); target=cl.map((v,i)=>v+0.5*(v-cd[i])); }
  const push=collectPushes();
  for(const a in push) target[+a-1]+=push[a];  // axis id is 1-based
  target=target.map(v=>Math.min(10,Math.max(0,v)));
  const excl=new Set(Object.keys(reactions));
  for(const t in watch) if(watch[t]==='seen'||watch[t]==='dropped') excl.add(t);
  const g=$('#recGenre').value;
  let allowed=g?new Set(showsWithGenre(g)):null;
  if(wlOnly){ const wl=new Set(Object.keys(watch).filter(t=>watch[t]==='watchlist')); allowed=allowed?new Set([...allowed].filter(t=>wl.has(t))):wl; }
  let recs=nearestTo(target,12,excl,allowed);
  let head='Recommended'; if(g) head+=' &middot; '+g; if(wlOnly) head+=' &middot; from watchlist'; if(neg.length) head+=' &middot; away from '+neg.length+' not-for-me';
  if(Object.keys(push).length) head+=' &middot; tuned to your reasons';
  if($('#sortQ').checked){ head+=' &middot; by quality'; recs=recs.slice().sort((a,b)=>(b.quality??-1)-(a.quality??-1)); }
  $('#recs').innerHTML=`<h2 style="margin-top:14px">${head}</h2>`+neighborList(recs,target);
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
  let html=`<h2 style="margin-top:14px">${head}</h2><ul class="list">`+shown.map(t=>rowItem(t,genresOf(t),SHOWS[t].quality,'')).join('')+'</ul>';
  if(matches.length>shown.length) html+=`<div class="dist">showing first ${shown.length}</div>`;
  $('#filterResults').innerHTML=html;
}

document.addEventListener('click',e=>{
  const w=e.target.closest('.why-t'); if(w){ const d=w.closest('li').querySelector('.why'); if(d) d.hidden=!d.hidden; return; }
  const rt=e.target.closest('.rsn-t'); if(rt){ const p=$('#chips .rsn[data-t="'+rt.dataset.rt+'"]'); if(p) p.classList.toggle('open'); return; }
  const rb=e.target.closest('.rsnb'); if(rb){ const t=decodeURIComponent(rb.dataset.t),k=rb.dataset.rsn,cur=reasons[t]||[]; reasons[t]=cur.includes(k)?cur.filter(x=>x!==k):[...cur,k]; if(!reasons[t].length) delete reasons[t]; saveReasons(); rb.classList.toggle('on'); if($('#recs').innerHTML) recommend(); return; }
  const rx=e.target.closest('.rxb'); if(rx){ setReaction(decodeURIComponent(rx.dataset.t),rx.dataset.rx); return; }
  const wx=e.target.closest('.wxb'); if(wx){ setWatch(decodeURIComponent(wx.dataset.t),wx.dataset.wx); return; }
  const lk=e.target.closest('.lk'); if(lk){ loadShow(decodeURIComponent(lk.dataset.t)); return; }
  const x=e.target.closest('.chip b[data-rm]'); if(x){ const t=decodeURIComponent(x.dataset.rm); delete reactions[t]; delete reasons[t]; saveReactions(); saveReasons(); renderChips(); if($('#pick').value) loadShow($('#pick').value); if($('#recs').innerHTML) recommend(); }
});
$('#pick').addEventListener('change',e=>{ if(e.target.value) loadShow(e.target.value); });
$('#simSameGenre').addEventListener('change',()=>{ if($('#pick').value) loadShow($('#pick').value); });
$('#addReact').addEventListener('click',()=>{ const v=$('#reactInput').value.trim(); if(v&&SHOWS[v]){ if(!reactions[v]){ reactions[v]='liked'; saveReactions(); } loadShow(v); renderChips(); } $('#reactInput').value=''; });
$('#reactInput').addEventListener('keydown',e=>{ if(e.key==='Enter') $('#addReact').click(); });
$('#recBtn').addEventListener('click',recommend);
$('#sortQ').addEventListener('change',()=>{ if($('#recs').innerHTML) recommend(); });
$('#wlOnly').addEventListener('change',()=>{ if($('#recs').innerHTML) recommend(); });
$('#clearBtn').addEventListener('click',()=>{ reactions={}; reasons={}; saveReactions(); saveReasons(); renderChips(); $('#recs').innerHTML=''; if($('#pick').value) loadShow($('#pick').value); });
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
            "quality": s.get("quality"),
            "quality_reason": s.get("quality_reason"),
            "summary": s.get("summary"),
            "episodes": s.get("episodes"),
            "seasons": s.get("seasons"),
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
    cli.cmd_load_quality(ns(db=str(DB), csv=str(REPO / "docs/quality.csv")))


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
