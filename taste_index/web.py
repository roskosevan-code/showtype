"""A tiny zero-dependency web UI for browsing taste-space.

Stdlib http.server only — no Flask, no build step. Serves a single page plus
a small JSON API backed by the same db/space modules the CLI uses.

    taste-index serve            # then open http://127.0.0.1:8000
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import db, space


def _values(vec: dict[int, int], axis_ids: list[int]) -> list[int]:
    return [vec[i] for i in axis_ids]


def _meta(conn) -> dict:
    axes = [
        {"id": int(r["id"]), "name": r["name"], "code": code}
        for r, code in zip(db.get_axes(conn), space.AXIS_CODES)
    ]
    titles = sorted(t for t in space.show_vectors(conn))
    return {"axes": axes, "shows": titles, "genres": db.get_genres(conn)}


def _show(conn, title: str) -> dict:
    rows = db.get_show_scores(conn, title)
    if not rows:
        raise KeyError(title)
    scores = [
        {
            "axis": r["axis"],
            "code": code,
            "value": r["value"],
            "confidence": r["confidence"],
            "justification": r["justification"],
        }
        for r, code in zip(rows, space.AXIS_CODES)
    ]
    m = db.get_show_meta(conn, title)
    meta = dict(m) if m else {}
    return {
        "title": title,
        "genres": db.genres_multi(conn).get(title, []),
        "quality": meta.get("quality"),
        "quality_reason": meta.get("quality_reason"),
        "summary": meta.get("summary"),
        "episodes": meta.get("episodes"),
        "seasons": meta.get("seasons"),
        "scores": scores,
    }


def _neighbor_list(items, axis_ids, gmulti, qmap):
    return [
        {"title": t, "distance": round(d, 2), "genres": gmulti.get(t, []),
         "quality": qmap.get(t), "values": _values(v, axis_ids)}
        for t, d, v in items
    ]


def _similar(conn, title: str, n: int, genre: str | None, same_genre: bool) -> dict:
    axis_ids, _ = space.axis_index(conn)
    gmulti = db.genres_multi(conn)
    qmap = db.quality_map(conn)
    allowed: set[str] | None = None
    if genre:
        allowed = db.shows_with_genre(conn, genre)
    elif same_genre:
        allowed = set().union(
            *(db.shows_with_genre(conn, g) for g in gmulti.get(title, [])) or [set()]
        )
    neighbors = space.nearest(conn, title, n=n, allowed=allowed)
    target = space.show_vectors(conn)[title]
    return {
        "title": title,
        "genres": gmulti.get(title, []),
        "values": _values(target, axis_ids),
        "neighbors": _neighbor_list(neighbors, axis_ids, gmulti, qmap),
    }


# Affinity reaction -> weight for the weighted-centroid recommender.
REACTION_WEIGHTS = {"loved": 2.0, "liked": 1.0}


def _recommend(conn, positives: dict[str, float], negatives: list[str], n: int,
               genre: str | None, axis_pushes: dict[int, float] | None = None,
               seen: set[str] | None = None, only: set[str] | None = None) -> dict:
    axis_ids, _ = space.axis_index(conn)
    gmulti = db.genres_multi(conn)
    qmap = db.quality_map(conn)
    allowed = db.shows_with_genre(conn, genre) if genre else None
    if only is not None:  # e.g. "from my watchlist only" — intersect with genre
        allowed = only if allowed is None else (allowed & only)
    present, neg, target, recs = space.recommend(
        conn, positives, n=n, allowed=allowed, negatives=negatives,
        axis_pushes=axis_pushes, exclude_extra=seen,
    )
    return {
        "liked": present,
        "disliked": neg,
        "centroid": [round(target[i], 1) for i in axis_ids],
        "recommendations": _neighbor_list(recs, axis_ids, gmulti, qmap),
    }


def _query(conn, constraints, limit: int = 60) -> dict:
    axis_ids, _ = space.axis_index(conn)
    gmulti = db.genres_multi(conn)
    qmap = db.quality_map(conn)
    matches = space.query(conn, constraints)
    items = [
        {"title": t, "genres": gmulti.get(t, []), "quality": qmap.get(t),
         "values": _values(v, axis_ids)}
        for t, v in matches
    ]
    return {"count": len(items), "matches": items[:limit]}


class _Handler(BaseHTTPRequestHandler):
    db_path = db.DEFAULT_DB_PATH

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code, body, content_type):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        conn = db.connect(self.db_path)
        try:
            if u.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if u.path == "/api/meta":
                return self._json(_meta(conn))
            if u.path == "/api/show":
                return self._json(_show(conn, q.get("title", [""])[0]))
            if u.path == "/api/similar":
                n = int(q.get("n", ["8"])[0])
                genre = q.get("genre", [""])[0] or None
                same = q.get("same_genre", ["0"])[0] == "1"
                return self._json(_similar(conn, q.get("title", [""])[0], n, genre, same))
            if u.path == "/api/recommend":
                positives = {}
                for reaction, weight in REACTION_WEIGHTS.items():
                    for t in q.get(reaction, [""])[0].split("|"):
                        if t:
                            positives[t] = weight
                negatives = [s for s in q.get("nope", [""])[0].split("|") if s]
                n = int(q.get("n", ["12"])[0])
                genre = q.get("genre", [""])[0] or None
                seen = {s for s in q.get("seen", [""])[0].split("|") if s} or None
                only = ({s for s in q.get("only", [""])[0].split("|") if s}
                        if "only" in q else None)
                pushes: dict[int, float] = {}
                for p in q.get("push", []):  # each "axisId,delta"
                    aid, _, delta = p.partition(",")
                    if aid and delta:
                        pushes[int(aid)] = pushes.get(int(aid), 0.0) + float(delta)
                return self._json(_recommend(
                    conn, positives, negatives, n, genre,
                    axis_pushes=pushes or None, seen=seen, only=only))
            if u.path == "/api/query":
                cons = []
                for f in q.get("f", []):
                    aid, lo, hi = (int(x) for x in f.split(","))
                    if lo > 0:
                        cons.append((aid, ">=", lo))
                    if hi < 10:
                        cons.append((aid, "<=", hi))
                return self._json(_query(conn, cons))
            return self._json({"error": "not found"}, 404)
        except (KeyError, ValueError) as e:
            return self._json({"error": str(e)}, 400)
        finally:
            conn.close()


def serve(db_path: str = db.DEFAULT_DB_PATH, host: str = "127.0.0.1", port: int = 8000):
    _Handler.db_path = db_path
    httpd = ThreadingHTTPServer((host, port), _Handler)
    print(f"The Taste Index — serving http://{host}:{port}  (db={db_path}, Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Taste Index</title>
<style>
  :root { --bg:#14110f; --card:#1d1916; --ink:#efe9e1; --mut:#9c9389; --acc:#c97b4a; --line:#332c26; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:22px 24px; border-bottom:1px solid var(--line); }
  h1 { margin:0; font:600 22px/1 Georgia,serif; letter-spacing:.2px; }
  .sub { color:var(--mut); font-size:13px; margin-top:4px; }
  .wrap { display:grid; grid-template-columns:1fr 1fr; gap:18px; padding:20px 24px; max-width:1100px; }
  @media (max-width:820px){ .wrap{ grid-template-columns:1fr; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; }
  .card h2 { margin:0 0 12px; font:600 13px/1 sans-serif; text-transform:uppercase; letter-spacing:.08em; color:var(--mut); }
  input, button { font:inherit; }
  input[type=text]{ width:100%; background:#0f0d0b; border:1px solid var(--line); color:var(--ink); padding:9px 11px; border-radius:7px; }
  button { background:var(--acc); color:#1a120c; border:0; padding:9px 13px; border-radius:7px; font-weight:600; cursor:pointer; }
  button.ghost { background:transparent; color:var(--mut); border:1px solid var(--line); }
  .row { display:flex; gap:8px; }
  .axes { margin-top:14px; }
  .ax { display:grid; grid-template-columns:120px 1fr 28px; align-items:center; gap:10px; margin:6px 0; }
  .ax .lbl { color:var(--mut); font-size:13px; }
  .bar { height:9px; background:#0f0d0b; border-radius:5px; overflow:hidden; }
  .bar > span { display:block; height:100%; background:var(--acc); }
  .ax .v { text-align:right; font-variant-numeric:tabular-nums; color:var(--ink); }
  .just { color:var(--mut); font-size:12.5px; margin:2px 0 10px 130px; }
  ul.list { list-style:none; margin:0; padding:0; }
  ul.list li { padding:7px 0; border-bottom:1px solid var(--line); }
  ul.list li:last-child { border-bottom:0; }
  .nrow { display:flex; justify-content:space-between; align-items:center; }
  .why { color:var(--mut); font-size:12.5px; margin:5px 0 2px; }
  .why b { color:var(--ink); font-weight:600; }
  .qb { border:1px solid var(--acc); color:var(--acc); border-radius:5px; padding:0 6px; font-size:11px; font-weight:600; margin-left:8px; }
  .summary { color:var(--ink); font-size:14px; margin:6px 0 2px; }
  .metaline { color:var(--mut); font-size:12.5px; margin-bottom:8px; }
  .qblock { margin-top:12px; padding:10px 12px; background:#0f0d0b; border:1px solid var(--line); border-radius:8px; font-size:13px; }
  .qblock b { color:var(--acc); }
  .lk { background:none; border:0; color:var(--acc); cursor:pointer; padding:0; font:inherit; text-align:left; }
  .dist { color:var(--mut); font-variant-numeric:tabular-nums; font-size:12.5px; }
  .badge { background:#0f0d0b; border:1px solid var(--line); color:var(--mut); border-radius:5px; padding:1px 7px; font-size:11.5px; margin-left:8px; }
  select { background:#0f0d0b; border:1px solid var(--line); color:var(--ink); padding:8px 10px; border-radius:7px; }
  label.chk { color:var(--mut); font-size:13px; display:flex; align-items:center; gap:6px; margin:10px 0 0; cursor:pointer; }
  .grid-full { grid-column:1 / -1; }
  .frow { display:grid; grid-template-columns:130px 1fr 1fr 62px; align-items:center; gap:12px; margin:5px 0; }
  .frow .lbl { color:var(--mut); font-size:13px; }
  .frow input[type=range]{ width:100%; accent-color:var(--acc); }
  .frd { text-align:right; color:var(--ink); font-variant-numeric:tabular-nums; font-size:12.5px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 10px; }
  .chip { background:#0f0d0b; border:1px solid var(--line); color:var(--ink); border-radius:20px; padding:3px 10px; font-size:12.5px; }
  .chip b { cursor:pointer; color:var(--mut); margin-left:6px; }
  .racts { display:flex; align-items:center; gap:6px; }
  .act { background:transparent; border:1px solid var(--line); color:var(--mut); width:22px; height:22px; border-radius:6px; cursor:pointer; padding:0; font-size:15px; line-height:1; }
  .act:hover { color:var(--ink); border-color:var(--acc); }
  .act.lk-on { color:var(--acc); border-color:var(--acc); }
  .rx { display:inline-flex; gap:1px; }
  .rxb { background:transparent; border:1px solid transparent; border-radius:5px; cursor:pointer; padding:1px 3px; font-size:14px; line-height:1; opacity:.45; }
  .rxb:hover { opacity:1; }
  .rxb.on { opacity:1; border-color:var(--acc); background:#0f0d0b; }
  .wx { display:inline-flex; align-items:center; margin-left:6px; padding-left:7px; border-left:1px solid var(--line); }
  .wxtog { background:transparent; border:1px solid transparent; border-radius:5px; cursor:pointer; padding:1px 4px; font-size:13px; line-height:1; color:var(--mut); opacity:.55; filter:grayscale(1); }
  .wxtog:hover { opacity:1; color:var(--ink); }
  .wxtog.set { opacity:1; filter:none; border-color:var(--acc); background:#0f0d0b; }
  .wxg { display:none; gap:1px; }
  .wx.open .wxg { display:inline-flex; }
  .wx.open .wxtog { display:none; }
  .wxb { background:transparent; border:1px solid transparent; border-radius:5px; cursor:pointer; padding:1px 3px; font-size:13px; line-height:1; opacity:.4; filter:grayscale(1); }
  .wxb:hover { opacity:.85; }
  .wxb.on { opacity:1; filter:none; border-color:var(--acc); background:#0f0d0b; }
  .rsn { display:none; width:100%; flex-basis:100%; gap:6px; flex-wrap:wrap; margin:1px 0 5px; }
  .rsn.open { display:flex; }
  .rsnb { background:#0f0d0b; border:1px solid var(--line); color:var(--mut); border-radius:20px; padding:2px 9px; font-size:12px; cursor:pointer; }
  .rsnb:hover { color:var(--ink); }
  .rsnb.on { color:var(--acc); border-color:var(--acc); }
  .chip b.rsn-t { color:var(--acc); font-weight:600; }
  .hint { color:var(--mut); font-size:12.5px; margin:-4px 0 10px; }
  .err { color:#e0795b; font-size:13px; }
</style></head>
<body>
<header><h1>The Taste Index</h1><div class="sub">Eight descriptive axes &middot; similarity and recommendation in taste-space</div></header>
<div class="wrap">
  <section class="card">
    <h2>Explore a show</h2>
    <input id="pick" type="text" list="shows" placeholder="Type a show&hellip;" autocomplete="off">
    <datalist id="shows"></datalist>
    <label class="chk"><input type="checkbox" id="simSameGenre"> Same genre only</label>
    <div id="profile"></div>
  </section>
  <section class="card">
    <h2>Your taste &rarr; recommendations</h2>
    <div class="hint">Rank a show &#10084;&#65039; loved &middot; &#128077; liked &middot; &#128581; never interested &middot; &#9209;&#65039; started &amp; stopped (best &rarr; worst). Track with &#128278; watchlist &middot; &#128065; seen. Anything you rank or mark seen is never recommended back; the last two rankings elicit &quot;why it didn&#39;t land&quot; reasons.</div>
    <div class="row"><input id="reactInput" type="text" list="shows" placeholder="Add a show, then react&hellip;" autocomplete="off"><button id="addReact">Add</button></div>
    <div id="chips" class="chips"></div>
    <div class="row"><button id="recBtn">Recommend</button><select id="recGenre"></select><button id="clearBtn" class="ghost">Clear</button></div>
    <label class="chk"><input type="checkbox" id="sortQ"> Sort by quality</label>
    <label class="chk"><input type="checkbox" id="wlOnly"> From my watchlist only</label>
    <div id="recs"></div>
  </section>
  <section class="card grid-full">
    <h2>Filter by axis profile</h2>
    <div id="filters"></div>
    <div class="row" style="margin-top:12px"><button id="applyFilter">Apply filter</button><button id="resetFilter" class="ghost">Reset</button></div>
    <div id="filterResults"></div>
  </section>
</div>
<script>
let AXES=[], GENRES=[], TITLESET=new Set();
// Single affinity ranking, best -> worst. loved/liked are positives; nope
// (never interested) is a blunt negative; dropped (started & stopped) is a
// negative that also elicits reason codes -> masked axis pushes.
const RX=[['loved','❤️','Loved'],['liked','👍','Liked'],['nope','🙅','Never interested'],['dropped','⏹️','Started & stopped']];
const WATCH=[['watchlist','🔖','Watchlist'],['seen','👁','Seen']];
// negative-only complaints -> per-axis push (axis id -> sign; +1 want more, -1 want less)
const COMPLAINTS=[['slow','Too slow',{1:1}],['dense','Hard to follow',{7:-1}],['cold',"Couldn't connect",{4:1}],['tryhard','Too try-hard',{5:-1}],['unreal',"Didn't buy it",{6:1}],['corny','Too corny',{8:-1,6:1}]];
const PUSH_STEP=1.5, PUSH_CAP=3;
let reactions=JSON.parse(localStorage.getItem('ti-reactions')||'{}');
let watch=JSON.parse(localStorage.getItem('ti-watch')||'{}');
let reasons=JSON.parse(localStorage.getItem('ti-reasons')||'{}');
const saveReactions=()=>localStorage.setItem('ti-reactions',JSON.stringify(reactions));
const saveWatch=()=>localStorage.setItem('ti-watch',JSON.stringify(watch));
const saveReasons=()=>localStorage.setItem('ti-reasons',JSON.stringify(reasons));
// Migrate the old model: 🚪 bounced watch-state -> ⏹️ reaction; a reasoned 👎
// (watched & disliked) -> ⏹️; drop the retired 😐 fine.
(function(){let m=false;
  for(const t in watch){ if(watch[t]==='dropped'){ if(!reactions[t]) reactions[t]='dropped'; delete watch[t]; m=true; } }
  for(const t in reactions){ if(reactions[t]==='nope'&&(reasons[t]||[]).length){ reactions[t]='dropped'; m=true; } else if(reactions[t]==='fine'){ delete reactions[t]; m=true; } }
  if(m){ saveReactions(); saveWatch(); }})();
const $=s=>document.querySelector(s);
const j=async u=>{const r=await fetch(u);return r.json();};

function bars(values){
  return '<div class="axes">'+AXES.map((a,i)=>{
    const v=values[i];
    return `<div class="ax"><span class="lbl">${a.name}</span><span class="bar"><span style="width:${v*10}%"></span></span><span class="v">${v}</span></div>`;
  }).join('')+'</div>';
}
const gbadges=gs=>(gs||[]).map(g=>`<span class="badge">${g}</span>`).join('');
const qbadge=q=>(q!=null)?`<span class="qb" title="Execution score">Q${q}</span>`:'';
const rxBtns=t=>{const e=encodeURIComponent(t),cur=reactions[t];return '<span class="rx">'+RX.map(([r,em,lbl])=>`<button class="rxb${cur===r?' on':''}" data-rx="${r}" data-t="${e}" title="${lbl}">${em}</button>`).join('')+'</span>';};
const wxBtns=t=>{const e=encodeURIComponent(t),cur=watch[t],cw=WATCH.find(w=>w[0]===cur);
  const tog=`<button class="wxtog${cur?' set':''}" data-wxtog="${e}" title="${cw?cw[2]:'Watch status'}">${cw?cw[1]:'&#9662;'}</button>`;
  const grp='<span class="wxg">'+WATCH.map(([w,em,lbl])=>`<button class="wxb${cur===w?' on':''}" data-wx="${w}" data-t="${e}" title="${lbl}">${em}</button>`).join('')+'</span>';
  return `<span class="wx">${tog}${grp}</span>`;};
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
function neighborList(items,ref){
  if(!items.length) return '<div class="dist">No matches.</div>';
  return '<ul class="list">'+items.map(it=>rowItem(it.title,it.genres,it.quality,`<span class="dist">${it.distance}</span>`, ref?whyText(it.values,ref):'')).join('')+'</ul>';
}

async function loadShow(title){
  $('#pick').value=title;
  const d=await j('/api/show?title='+encodeURIComponent(title));
  if(d.error){ $('#profile').innerHTML='<div class="err">'+d.error+'</div>'; return; }
  const sameG=$('#simSameGenre').checked?'&same_genre=1':'';
  const sim=await j('/api/similar?n=8&title='+encodeURIComponent(title)+sameG);
  let html=`<div style="margin:8px 0 2px">${gbadges(d.genres)}${qbadge(d.quality)} ${rxBtns(title)}${wxBtns(title)}</div>`;
  if(d.summary) html+=`<div class="summary">${d.summary}</div>`;
  const meta=[]; if(d.episodes) meta.push('&approx;'+d.episodes+' episodes'); if(d.seasons) meta.push(d.seasons+' season'+(d.seasons===1?'':'s'));
  if(meta.length) html+=`<div class="metaline">${meta.join(' &middot; ')}</div>`;
  html+=bars(d.scores.map(s=>s.value));
  html+=d.scores.map(s=>`<div class="just"><b>${s.axis} ${s.value}</b> &middot; ${s.justification} <i>(${s.confidence})</i></div>`).join('');
  if(d.quality!=null) html+=`<div class="qblock"><b>Execution ${d.quality}/10</b> &middot; ${d.quality_reason||''}</div>`;
  html+='<h2 style="margin-top:16px">Nearest in taste-space</h2>'+neighborList(sim.neighbors, sim.values);
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
  const reacted=Object.keys(reactions);
  const wl=Object.keys(watch).filter(t=>watch[t]==='watchlist');
  const head=wl.length?`<div class="hint" style="margin:0 0 8px">&#128278; ${wl.length} on your watchlist</div>`:'';
  if(!reacted.length){ $('#chips').innerHTML=head+'<span class="dist">No reactions yet — use the &#10084;&#65039;&#128077;&#128581;&#9209;&#65039; on any show.</span>'; return; }
  const ord={loved:0,liked:1,nope:2,dropped:3}, em=r=>RX.find(x=>x[0]===r)[1];
  reacted.sort((a,b)=>(ord[reactions[a]]-ord[reactions[b]])||a.localeCompare(b));
  // Only "Started & stopped" (⏹️) carries the "why it didn't land" reason editor.
  const items=reacted.map(t=>({t,emo:em(reactions[t]),why:reactions[t]==='dropped'}));
  $('#chips').innerHTML=head+items.map(({t,emo,why})=>{
    const e=encodeURIComponent(t);
    let s=`<span class="chip">${emo} ${t}`;
    if(why){ const n=(reasons[t]||[]).length; s+=`<b class="rsn-t" data-rt="${e}" title="Why it didn't land">${n?'why&middot;'+n:'why'}</b>`; }
    s+=`<b data-rm="${e}">&times;</b></span>`;
    if(why) s+=complaintRow(t);
    return s;
  }).join('');
}

function buildFilters(){
  $('#filters').innerHTML=AXES.map(a=>
    `<div class="frow" data-axis="${a.id}"><span class="lbl">${a.name}</span>`+
    `<input type="range" min="0" max="10" value="0" data-kind="min">`+
    `<input type="range" min="0" max="10" value="10" data-kind="max">`+
    `<span class="frd" id="frd-${a.id}">0&ndash;10</span></div>`).join('');
}
function syncPair(el){
  const row=el.closest('.frow'); const mn=row.querySelector('[data-kind=min]'), mx=row.querySelector('[data-kind=max]');
  if(+mn.value>+mx.value){ if(el.dataset.kind==='min') mx.value=mn.value; else mn.value=mx.value; }
  $('#frd-'+row.dataset.axis).innerHTML=mn.value+'&ndash;'+mx.value;
}
function axisFilters(){
  return [...document.querySelectorAll('.frow')].map(r=>({
    id:+r.dataset.axis, min:+r.querySelector('[data-kind=min]').value, max:+r.querySelector('[data-kind=max]').value
  }));
}
async function runQuery(){
  const fs=axisFilters().filter(s=>s.min>0||s.max<10);
  const d=await j('/api/query?'+fs.map(s=>`f=${s.id},${s.min},${s.max}`).join('&'));
  const head=`${d.count} show${d.count===1?'':'s'} match`+(fs.length?'':' (no filter)');
  let html=`<h2 style="margin-top:14px">${head}</h2><ul class="list">`+
    d.matches.map(m=>rowItem(m.title,m.genres,m.quality,'')).join('')+'</ul>';
  if(d.count>d.matches.length) html+=`<div class="dist">showing first ${d.matches.length}</div>`;
  $('#filterResults').innerHTML=html;
}
function collectPushes(){
  // Aggregate complaint pushes across negatively-marked shows; cap per axis.
  const push={};
  const add=t=>(reasons[t]||[]).forEach(k=>{ const c=COMPLAINTS.find(x=>x[0]===k); if(c) for(const a in c[2]) push[a]=(push[a]||0)+c[2][a]*PUSH_STEP; });
  for(const t in reactions) if(reactions[t]==='dropped'&&(reasons[t]||[]).length) add(t);
  for(const a in push) push[a]=Math.max(-PUSH_CAP,Math.min(PUSH_CAP,push[a]));
  return push;
}
async function recommend(){
  const groups={loved:[],liked:[],nope:[],dropped:[]};
  for(const t in reactions){ if(groups[reactions[t]]) groups[reactions[t]].push(t); }
  if(!groups.loved.length&&!groups.liked.length){ $('#recs').innerHTML='<div class="dist">React to a few shows you liked first (&#10084;&#65039; or &#128077;).</div>'; return; }
  // Never-interested (🙅) and unreasoned started&stopped (⏹️) push away bluntly;
  // reasoned ⏹️ steers via masked axis pushes and is just excluded via `seen`.
  const seen=new Set(Object.keys(watch).filter(t=>watch[t]==='seen'));
  const blunt=[...groups.nope];
  groups.dropped.forEach(t=>{ if((reasons[t]||[]).length) seen.add(t); else blunt.push(t); });
  const push=collectPushes();
  const g=$('#recGenre').value;
  const wlOnly=$('#wlOnly').checked;
  if(wlOnly && !Object.keys(watch).some(t=>watch[t]==='watchlist')){ $('#recs').innerHTML='<div class="dist">Nothing on your watchlist yet — mark shows with &#128278;.</div>'; return; }
  const p=new URLSearchParams({n:'12'});
  ['loved','liked'].forEach(r=>{ if(groups[r].length) p.set(r,groups[r].join('|')); });
  if(blunt.length) p.set('nope',blunt.join('|'));
  if(g) p.set('genre',g);
  if(seen.size) p.set('seen',[...seen].join('|'));
  if(wlOnly) p.set('only',Object.keys(watch).filter(t=>watch[t]==='watchlist').join('|'));
  for(const a in push) p.append('push',a+','+push[a]);
  const d=await j('/api/recommend?'+p.toString());
  if(d.error){ $('#recs').innerHTML='<div class="err">'+d.error+'</div>'; return; }
  let head='Recommended'; if(g) head+=' &middot; '+g; if(wlOnly) head+=' &middot; from watchlist';
  if(d.disliked&&d.disliked.length) head+=' &middot; away from '+d.disliked.length+' you rejected';
  if(Object.keys(push).length) head+=' &middot; tuned to your reasons';
  let recs=d.recommendations;
  if($('#sortQ').checked){ head+=' &middot; by quality'; recs=recs.slice().sort((a,b)=>(b.quality??-1)-(a.quality??-1)); }
  $('#recs').innerHTML=`<h2 style="margin-top:14px">${head}</h2>`+neighborList(recs, d.centroid);
}

document.addEventListener('click',e=>{
  const w=e.target.closest('.why-t'); if(w){ const d=w.closest('li').querySelector('.why'); if(d) d.hidden=!d.hidden; return; }
  const rt=e.target.closest('.rsn-t'); if(rt){ const p=$('#chips .rsn[data-t="'+rt.dataset.rt+'"]'); if(p) p.classList.toggle('open'); return; }
  const rb=e.target.closest('.rsnb'); if(rb){ const t=decodeURIComponent(rb.dataset.t),k=rb.dataset.rsn,cur=reasons[t]||[]; reasons[t]=cur.includes(k)?cur.filter(x=>x!==k):[...cur,k]; const n=reasons[t].length; if(!n) delete reasons[t]; saveReasons(); rb.classList.toggle('on'); const tag=document.querySelector('#chips .rsn-t[data-rt="'+rb.dataset.t+'"]'); if(tag) tag.innerHTML=n?('why&middot;'+n):'why'; if($('#recs').innerHTML) recommend(); return; }
  const rx=e.target.closest('.rxb'); if(rx){ setReaction(decodeURIComponent(rx.dataset.t),rx.dataset.rx); return; }
  const wt=e.target.closest('.wxtog'); if(wt){ wt.closest('.wx').classList.toggle('open'); return; }
  const wx=e.target.closest('.wxb'); if(wx){ setWatch(decodeURIComponent(wx.dataset.t),wx.dataset.wx); return; }
  const lk=e.target.closest('.lk'); if(lk){ loadShow(decodeURIComponent(lk.dataset.t)); return; }
  const x=e.target.closest('.chip b[data-rm]'); if(x){ const t=decodeURIComponent(x.dataset.rm); delete reactions[t]; delete reasons[t]; saveReactions(); saveReasons(); renderChips(); if($('#pick').value) loadShow($('#pick').value); if($('#recs').innerHTML) recommend(); return; }
  const xw=e.target.closest('.chip b[data-rmw]'); if(xw){ const t=decodeURIComponent(xw.dataset.rmw); delete watch[t]; delete reasons[t]; saveWatch(); saveReasons(); renderChips(); if($('#pick').value) loadShow($('#pick').value); if($('#recs').innerHTML) recommend(); }
});
$('#pick').addEventListener('change',e=>{ if(e.target.value) loadShow(e.target.value); });
$('#simSameGenre').addEventListener('change',()=>{ if($('#pick').value) loadShow($('#pick').value); });
$('#addReact').addEventListener('click',()=>{ const v=$('#reactInput').value.trim(); if(v&&TITLESET.has(v)){ if(!reactions[v]){ reactions[v]='liked'; saveReactions(); } loadShow(v); renderChips(); } $('#reactInput').value=''; });
$('#reactInput').addEventListener('keydown',e=>{ if(e.key==='Enter') $('#addReact').click(); });
$('#recBtn').addEventListener('click',recommend);
$('#sortQ').addEventListener('change',()=>{ if($('#recs').innerHTML) recommend(); });
$('#wlOnly').addEventListener('change',()=>{ if($('#recs').innerHTML) recommend(); });
$('#clearBtn').addEventListener('click',()=>{ reactions={}; reasons={}; saveReactions(); saveReasons(); renderChips(); $('#recs').innerHTML=''; if($('#pick').value) loadShow($('#pick').value); });
$('#filters').addEventListener('input',e=>{ if(e.target.type==='range') syncPair(e.target); });
$('#applyFilter').addEventListener('click',runQuery);
$('#resetFilter').addEventListener('click',()=>{ document.querySelectorAll('.frow').forEach(r=>{ r.querySelector('[data-kind=min]').value=0; r.querySelector('[data-kind=max]').value=10; $('#frd-'+r.dataset.axis).innerHTML='0&ndash;10'; }); $('#filterResults').innerHTML=''; });

(async()=>{
  const m=await j('/api/meta');
  AXES=m.axes; GENRES=m.genres||[]; TITLESET=new Set(m.shows);
  $('#shows').innerHTML=m.shows.map(s=>`<option value="${s.replace(/"/g,'&quot;')}">`).join('');
  $('#recGenre').innerHTML='<option value="">All genres</option>'+GENRES.map(g=>`<option value="${g}">${g}</option>`).join('');
  renderChips();
  buildFilters();
})();
</script>
</body></html>"""
