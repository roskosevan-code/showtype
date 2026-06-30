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
    axis_ids, _ = space.axis_index(conn)
    axes = [
        {"id": int(r["id"]), "name": r["name"], "code": code}
        for r, code in zip(db.get_axes(conn), space.AXIS_CODES)
    ]
    titles = sorted(t for t in space.show_vectors(conn))
    return {"axes": axes, "shows": titles}


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
    return {"title": title, "scores": scores}


def _neighbor_list(conn, items, axis_ids):
    return [
        {"title": t, "distance": round(d, 2), "values": _values(v, axis_ids)}
        for t, d, v in items
    ]


def _similar(conn, title: str, n: int) -> dict:
    axis_ids, _ = space.axis_index(conn)
    neighbors = space.nearest(conn, title, n=n)
    target = space.show_vectors(conn)[title]
    return {
        "title": title,
        "values": _values(target, axis_ids),
        "neighbors": _neighbor_list(conn, neighbors, axis_ids),
    }


def _recommend(conn, liked: list[str], n: int) -> dict:
    axis_ids, _ = space.axis_index(conn)
    present, centroid, recs = space.recommend(conn, liked, n=n)
    return {
        "liked": present,
        "centroid": [round(centroid[i], 1) for i in axis_ids],
        "recommendations": _neighbor_list(conn, recs, axis_ids),
    }


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
                return self._json(_similar(conn, q.get("title", [""])[0], n))
            if u.path == "/api/recommend":
                liked = [s for s in q.get("like", [""])[0].split("|") if s]
                n = int(q.get("n", ["12"])[0])
                return self._json(_recommend(conn, liked, n))
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
  ul.list li { display:flex; justify-content:space-between; align-items:center; padding:7px 0; border-bottom:1px solid var(--line); }
  ul.list li:last-child { border-bottom:0; }
  .lk { background:none; border:0; color:var(--acc); cursor:pointer; padding:0; font:inherit; text-align:left; }
  .dist { color:var(--mut); font-variant-numeric:tabular-nums; font-size:12.5px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 10px; }
  .chip { background:#0f0d0b; border:1px solid var(--line); color:var(--ink); border-radius:20px; padding:3px 10px; font-size:12.5px; }
  .chip b { cursor:pointer; color:var(--mut); margin-left:6px; }
  .err { color:#e0795b; font-size:13px; }
</style></head>
<body>
<header><h1>The Taste Index</h1><div class="sub">Eight descriptive axes &middot; similarity and recommendation in taste-space</div></header>
<div class="wrap">
  <section class="card">
    <h2>Explore a show</h2>
    <input id="pick" type="text" list="shows" placeholder="Type a show&hellip;" autocomplete="off">
    <datalist id="shows"></datalist>
    <div id="profile"></div>
  </section>
  <section class="card">
    <h2>Recommend from shows you like</h2>
    <div class="row"><input id="likeInput" type="text" list="shows" placeholder="Add a show you like&hellip;" autocomplete="off"><button id="addLike">Add</button></div>
    <div id="chips" class="chips"></div>
    <div class="row"><button id="recBtn">Recommend</button><button id="clearBtn" class="ghost">Clear</button></div>
    <div id="recs"></div>
  </section>
</div>
<script>
let AXES=[];
const liked=[];
const $=s=>document.querySelector(s);
const j=async u=>{const r=await fetch(u);return r.json();};

function bars(values){
  return '<div class="axes">'+AXES.map((a,i)=>{
    const v=values[i];
    return `<div class="ax"><span class="lbl">${a.name}</span><span class="bar"><span style="width:${v*10}%"></span></span><span class="v">${v}</span></div>`;
  }).join('')+'</div>';
}
function neighborList(items, fn){
  return '<ul class="list">'+items.map(it=>
    `<li><button class="lk" data-t="${encodeURIComponent(it.title)}">${it.title}</button><span class="dist">${it.distance}</span></li>`
  ).join('')+'</ul>';
}

async function loadShow(title){
  $('#pick').value=title;
  const d=await j('/api/show?title='+encodeURIComponent(title));
  if(d.error){ $('#profile').innerHTML='<div class="err">'+d.error+'</div>'; return; }
  const sim=await j('/api/similar?title='+encodeURIComponent(title)+'&n=8');
  let html=bars(d.scores.map(s=>s.value));
  html+=d.scores.map(s=>`<div class="just"><b>${s.axis} ${s.value}</b> &middot; ${s.justification} <i>(${s.confidence})</i></div>`).join('');
  html+='<h2 style="margin-top:16px">Nearest in taste-space</h2>'+neighborList(sim.neighbors);
  $('#profile').innerHTML=html;
}

function renderChips(){
  $('#chips').innerHTML=liked.map((t,i)=>`<span class="chip">${t}<b data-i="${i}">&times;</b></span>`).join('')||'<span class="dist">No shows added yet.</span>';
}
async function recommend(){
  if(!liked.length){ $('#recs').innerHTML='<div class="dist">Add a few shows first.</div>'; return; }
  const d=await j('/api/recommend?n=12&like='+liked.map(encodeURIComponent).join('|'));
  if(d.error){ $('#recs').innerHTML='<div class="err">'+d.error+'</div>'; return; }
  $('#recs').innerHTML='<h2 style="margin-top:14px">Recommended</h2>'+neighborList(d.recommendations);
}

document.addEventListener('click',e=>{
  const lk=e.target.closest('.lk'); if(lk){ loadShow(decodeURIComponent(lk.dataset.t)); }
  const x=e.target.closest('.chip b'); if(x){ liked.splice(+x.dataset.i,1); renderChips(); }
});
$('#pick').addEventListener('change',e=>{ if(e.target.value) loadShow(e.target.value); });
$('#addLike').addEventListener('click',()=>{ const v=$('#likeInput').value.trim(); if(v&&!liked.includes(v)){ liked.push(v); renderChips(); } $('#likeInput').value=''; });
$('#likeInput').addEventListener('keydown',e=>{ if(e.key==='Enter') $('#addLike').click(); });
$('#recBtn').addEventListener('click',recommend);
$('#clearBtn').addEventListener('click',()=>{ liked.length=0; renderChips(); $('#recs').innerHTML=''; });

(async()=>{
  const m=await j('/api/meta');
  AXES=m.axes;
  $('#shows').innerHTML=m.shows.map(s=>`<option value="${s.replace(/"/g,'&quot;')}">`).join('');
  renderChips();
})();
</script>
</body></html>"""
