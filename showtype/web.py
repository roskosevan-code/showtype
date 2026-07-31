"""A tiny zero-dependency web UI for browsing taste-space.

Stdlib http.server only — no Flask, no build step. Serves a single page plus
a small JSON API backed by the same db/space modules the CLI uses.

    showtype serve            # then open http://127.0.0.1:8000
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
    print(f"Show Type — serving http://{host}:{port}  (db={db_path}, Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


# ---------------------------------------------------------------------------
# The page, split in three so scripts/build_static.py can reuse the UI layer:
#   PAGE_HEAD         — doctype, CSS, markup (no <script>)
#   SERVED_ENGINE_JS  — data access via fetch()/the JSON API
#   UI_JS             — all rendering/state/events; talks only to `ENGINE`
# The offline build swaps SERVED_ENGINE_JS for a local-compute engine over an
# embedded DATA blob and reuses PAGE_HEAD + UI_JS verbatim.
# ---------------------------------------------------------------------------

PAGE_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#131010">
<title>Show Type</title>
<style>
  :root{
    --bg:#131010; --bg2:#1a1613; --card:#1e1915; --raise:#282119;
    --ink:#f3ede4; --mut:#a2968a; --faint:#7a6f64;
    --acc:#d98a54; --acc-ink:#231204;
    --line:#322b25; --line2:#413830; --err:#e0795b; --rad:16px;
  }
  *{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html{ color-scheme:dark; }
  body{ margin:0; background:var(--bg); color:var(--ink);
        font:16px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
        padding-bottom:calc(84px + env(safe-area-inset-bottom)); }
  button{ font:inherit; color:inherit; cursor:pointer; }
  header{ position:sticky; top:0; z-index:30; background:rgba(19,16,16,.88);
          backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
          border-bottom:1px solid var(--line); }
  .hrow{ max-width:960px; margin:0 auto; padding:14px 18px;
         display:flex; align-items:baseline; justify-content:space-between; gap:12px; }
  h1{ margin:0; font:700 19px/1 Georgia,'Times New Roman',serif; letter-spacing:.2px; }
  .hcount{ color:var(--faint); font-size:12.5px; }
  nav{ position:fixed; left:0; right:0; bottom:0; z-index:30; display:flex;
       background:rgba(24,20,17,.93); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
       border-top:1px solid var(--line); padding:8px 10px calc(8px + env(safe-area-inset-bottom)); }
  .tab{ flex:1; display:flex; flex-direction:column; align-items:center; gap:3px;
        background:none; border:0; color:var(--mut); font-size:11px; font-weight:600;
        padding:4px 0; border-radius:12px; }
  .tab .ticon{ font-size:21px; line-height:1; filter:grayscale(1); opacity:.65; transition:.15s; }
  .tab.on{ color:var(--acc); }
  .tab.on .ticon{ filter:none; opacity:1; }
  main{ max-width:960px; margin:0 auto; padding:14px 16px 40px; }
  .panel{ display:none; }
  .panel.on{ display:block; animation:fade .18s ease; }
  @keyframes fade{ from{opacity:0; transform:translateY(5px);} to{opacity:1; transform:none;} }
  @media(min-width:760px){
    body{ padding-bottom:48px; }
    nav{ position:static; background:none; border:0; backdrop-filter:none;
         max-width:960px; margin:14px auto -2px; padding:0 16px; gap:8px; justify-content:flex-start; }
    .tab{ flex:0 0 auto; flex-direction:row; gap:8px; font-size:14px; padding:9px 18px;
          border:1px solid var(--line); border-radius:999px; background:var(--card); }
    .tab .ticon{ font-size:16px; }
    .tab.on{ background:var(--acc); border-color:var(--acc); color:var(--acc-ink); }
  }
  .search{ position:relative; margin:6px 0 4px; }
  input[type=search]{ width:100%; font-size:16px; background:var(--card);
    border:1px solid var(--line2); color:var(--ink); padding:13px 16px;
    border-radius:14px; outline:none; -webkit-appearance:none; appearance:none; }
  input[type=search]:focus{ border-color:var(--acc); }
  input[type=search]::placeholder{ color:var(--faint); }
  .suggest{ position:absolute; top:calc(100% + 6px); left:0; right:0; z-index:40;
    background:var(--raise); border:1px solid var(--line2); border-radius:14px;
    overflow:hidden auto; max-height:55vh; box-shadow:0 14px 34px rgba(0,0,0,.5); }
  .suggest button{ display:block; width:100%; text-align:left; background:none; border:0;
    padding:12px 16px; font-size:15px; border-bottom:1px solid var(--line); }
  .suggest button:last-child{ border-bottom:0; }
  .suggest button:hover{ background:var(--card); }
  .controls{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; align-items:center; }
  .pill{ display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line);
    background:var(--card); border-radius:999px; padding:9px 15px; font-size:13.5px;
    color:var(--mut); cursor:pointer; user-select:none; }
  .pill input{ display:none; }
  .pill.on{ border-color:var(--acc); color:var(--ink); background:rgba(217,138,84,.12); }
  select{ background:var(--card); border:1px solid var(--line); color:var(--ink);
    padding:9px 32px 9px 15px; border-radius:999px; font-size:13.5px;
    appearance:none; -webkit-appearance:none;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23a2968a' fill='none' stroke-width='1.5'/%3E%3C/svg%3E");
    background-repeat:no-repeat; background-position:right 13px center; }
  .row{ display:flex; gap:10px; margin:12px 0; }
  .primary{ flex:1; background:var(--acc); color:var(--acc-ink); border:0;
    padding:13px 18px; border-radius:13px; font-weight:700; font-size:15px; }
  .primary:active{ transform:scale(.99); }
  .ghost{ background:none; border:1px solid var(--line2); color:var(--mut);
    border-radius:13px; padding:12px 16px; font-size:14px; }
  .ghost.wide{ width:100%; margin-top:14px; }
  .lh{ margin:20px 2px 8px; font:600 12.5px/1.3 sans-serif; text-transform:uppercase;
    letter-spacing:.09em; color:var(--faint); }
  .lh .mut{ text-transform:none; letter-spacing:0; font-weight:400; color:var(--mut); }
  .hint{ color:var(--mut); font-size:14px; margin:10px 2px; }
  .err{ color:var(--err); font-size:14px; margin:10px 2px; }
  .empty{ border:1px dashed var(--line2); border-radius:var(--rad); padding:24px 18px;
    color:var(--mut); font-size:14px; text-align:center; margin:16px 0; }
  ul.list{ list-style:none; margin:8px 0; padding:0; background:var(--card);
    border:1px solid var(--line); border-radius:var(--rad); overflow:hidden; }
  ul.list li{ border-bottom:1px solid var(--line); }
  ul.list li:last-child{ border-bottom:0; }
  .item{ display:flex; align-items:center; gap:12px; width:100%; min-height:58px;
    background:none; border:0; text-align:left; padding:12px 14px; }
  .item:active{ background:var(--raise); }
  .imain{ flex:1; min-width:0; }
  .ttl{ display:block; font-weight:600; font-size:15.5px; line-height:1.35; }
  .isub{ display:flex; flex-wrap:wrap; gap:2px 10px; color:var(--mut);
    font-size:12.5px; margin-top:2px; }
  .qb{ color:var(--acc); font-weight:600; }
  .dist{ color:var(--faint); font-variant-numeric:tabular-nums; }
  .state{ flex:0 0 auto; font-size:14px; letter-spacing:2px; }
  .chev{ flex:0 0 auto; color:var(--faint); font-size:18px; }
  .hero{ background:var(--card); border:1px solid var(--line); border-radius:var(--rad);
    padding:18px; margin:12px 0 4px; }
  .hero h3{ margin:0 0 8px; font:700 22px/1.25 Georgia,'Times New Roman',serif; }
  .badges{ display:flex; flex-wrap:wrap; gap:6px; margin:2px 0 4px; }
  .badge{ background:var(--raise); border:1px solid var(--line); color:var(--mut);
    border-radius:999px; padding:3px 11px; font-size:12px; }
  .badge.q{ color:var(--acc); border-color:rgba(217,138,84,.45); }
  .summary{ font-size:14.5px; margin:10px 0 4px; }
  .metaline{ color:var(--faint); font-size:13px; margin:4px 0; }
  .whybox{ background:var(--raise); border-radius:12px; padding:10px 14px;
    font-size:13.5px; color:var(--mut); margin:12px 0 4px; }
  .whybox b{ color:var(--ink); }
  .sec h4{ margin:16px 0 8px; font:600 11.5px/1 sans-serif; text-transform:uppercase;
    letter-spacing:.1em; color:var(--faint); }
  .seg{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .segb{ display:flex; align-items:center; justify-content:center; gap:8px;
    min-height:46px; background:var(--bg2); border:1px solid var(--line);
    color:var(--mut); border-radius:12px; padding:10px 6px; font-size:13.5px; }
  .segb .em{ font-size:17px; }
  .segb.on{ background:rgba(217,138,84,.14); border-color:var(--acc); color:var(--ink); }
  .rsnlbl{ color:var(--mut); font-size:13px; margin:12px 0 7px; }
  .rsn{ display:flex; flex-wrap:wrap; gap:7px; }
  .rsnb{ background:var(--bg2); border:1px solid var(--line); color:var(--mut);
    border-radius:999px; padding:8px 14px; font-size:13px; min-height:36px; }
  .rsnb.on{ color:var(--acc); border-color:var(--acc); background:rgba(217,138,84,.1); }
  .axes{ margin:4px 0; }
  .ax{ display:grid; grid-template-columns:112px 1fr 24px; align-items:center;
    gap:10px; margin:7px 0; font-size:13px; }
  .ax .lbl{ color:var(--mut); }
  .bar{ height:8px; background:var(--raise); border-radius:4px; overflow:hidden; }
  .bar>span{ display:block; height:100%; border-radius:4px;
    background:linear-gradient(90deg,#a5623a,var(--acc)); }
  .ax .v{ text-align:right; font-variant-numeric:tabular-nums; }
  .qblock{ margin-top:14px; padding:11px 14px; background:var(--raise);
    border-radius:12px; font-size:13.5px; color:var(--mut); }
  .qblock b{ color:var(--acc); }
  details.just{ margin-top:14px; border-top:1px solid var(--line); padding-top:12px; }
  details.just summary{ cursor:pointer; color:var(--mut); font-size:13.5px; }
  .jrow{ color:var(--mut); font-size:13px; margin:9px 0; }
  .jrow b{ color:var(--ink); }
  .glab{ margin:18px 2px 8px; font:600 12px/1 sans-serif; text-transform:uppercase;
    letter-spacing:.09em; color:var(--faint); }
  .chips{ display:flex; flex-wrap:wrap; gap:8px; }
  .chip{ display:inline-flex; align-items:center; gap:7px; max-width:100%;
    background:var(--card); border:1px solid var(--line); border-radius:999px;
    padding:6px 7px 6px 14px; font-size:13.5px; }
  .chip .nm{ background:none; border:0; padding:0; display:inline-flex; gap:6px;
    align-items:center; min-width:0; }
  .chip .nm .tx{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:52vw; }
  .chip .why{ color:var(--acc); font-size:12px; font-weight:600; }
  .chip .rm{ display:inline-flex; align-items:center; justify-content:center;
    width:26px; height:26px; border-radius:50%; background:var(--raise); border:0;
    color:var(--mut); font-size:12px; flex:0 0 auto; }
  .wline{ color:var(--mut); font-size:13.5px; margin:12px 2px; }
  .frow{ margin:16px 0; }
  .fhead{ display:flex; justify-content:space-between; align-items:baseline;
    font-size:13.5px; color:var(--mut); margin-bottom:2px; }
  .frd{ color:var(--faint); font-variant-numeric:tabular-nums; }
  .frd.set{ color:var(--acc); font-weight:600; }
  .fr2{ display:grid; grid-template-columns:34px 1fr; align-items:center; gap:8px;
    font-size:11px; color:var(--faint); }
  input[type=range]{ width:100%; accent-color:var(--acc); height:30px; margin:0; }
  #scrim{ position:fixed; inset:0; z-index:50; background:rgba(0,0,0,.55);
    opacity:0; transition:opacity .2s; }
  #scrim.on{ opacity:1; }
  #sheet{ position:fixed; left:0; right:0; bottom:0; z-index:60; background:var(--bg2);
    border:1px solid var(--line2); border-bottom:0; border-radius:22px 22px 0 0;
    max-height:88vh; overflow-y:auto; overscroll-behavior:contain;
    padding:8px 18px calc(24px + env(safe-area-inset-bottom));
    transform:translateY(105%); transition:transform .25s cubic-bezier(.2,.9,.3,1);
    box-shadow:0 -18px 50px rgba(0,0,0,.55); }
  #sheet.on{ transform:none; }
  .grab{ width:44px; height:5px; border-radius:3px; background:var(--line2); margin:6px auto 12px; }
  @media(min-width:760px){
    #sheet{ left:50%; right:auto; bottom:auto; top:50%; width:540px; max-height:82vh;
      border-radius:20px; border-bottom:1px solid var(--line2);
      transform:translate(-50%,-46%); opacity:0; pointer-events:none;
      transition:transform .2s ease, opacity .2s ease; }
    #sheet.on{ transform:translate(-50%,-50%); opacity:1; pointer-events:auto; }
    .grab{ display:none; }
    .chip .nm .tx{ max-width:340px; }
  }
  .shead{ display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
  .shead h3{ margin:2px 0 8px; font:700 20px/1.3 Georgia,'Times New Roman',serif; }
  .x{ flex:0 0 auto; width:36px; height:36px; border-radius:50%;
    background:var(--card); border:1px solid var(--line); color:var(--mut); font-size:15px; }
  .ab{ background:var(--card); border:1px solid var(--line); border-radius:var(--rad);
    padding:18px; margin:12px 0; }
  .ab h3{ margin:0 0 6px; font:700 19px/1.3 Georgia,'Times New Roman',serif; }
  .ab p{ margin:9px 0; font-size:14.5px; }
  .ab p.mut{ color:var(--mut); font-size:13.5px; }
  .ab a{ color:var(--acc); text-decoration:none; border-bottom:1px solid rgba(217,138,84,.4); }
  .ab a:hover{ border-bottom-color:var(--acc); }
  .ab p:last-child{ margin-bottom:0; }
  ol.steps{ margin:10px 0 2px; padding-left:19px; }
  ol.steps li{ margin:9px 0; font-size:14.5px; }
  ol.steps li::marker{ color:var(--faint); font-size:13px; }
  ol.steps b{ color:var(--acc); }
  ul.facts{ list-style:none; margin:8px 0 0; padding:0; }
  ul.facts li{ position:relative; padding-left:16px; margin:9px 0;
    font-size:13.5px; color:var(--mut); }
  ul.facts li::before{ content:'\\2022'; position:absolute; left:2px; color:var(--acc); }
  ul.facts b{ color:var(--ink); font-weight:600; }
  .axd{ border-top:1px solid var(--line); padding:13px 0 4px; }
  .axd:first-child{ border-top:0; padding-top:4px; }
  .axd .an{ font-weight:600; font-size:15px; }
  .axd .an i{ color:var(--faint); font-style:normal; font-size:12.5px; font-weight:400; }
  .axd .ad{ color:var(--mut); font-size:13.5px; margin:3px 0 7px; }
  .poles{ display:flex; justify-content:space-between; gap:12px;
    font-size:11.5px; color:var(--faint); }
  .poles span{ flex:1 1 0; }
  .poles .hi{ text-align:right; }
</style></head>
<body>
<header><div class="hrow"><h1>Show Type</h1><span class="hcount" id="count"></span></div></header>
<nav>
  <button class="tab on" data-tab="explore"><span class="ticon">&#128269;</span>Explore</button>
  <button class="tab" data-tab="foryou"><span class="ticon">&#10024;</span>For You</button>
  <button class="tab" data-tab="browse"><span class="ticon">&#127898;&#65039;</span>Browse</button>
  <button class="tab" data-tab="about"><span class="ticon">&#8505;&#65039;</span>About</button>
</nav>
<main>
  <section id="panel-explore" class="panel on">
    <div class="search"><input id="pick" type="search" placeholder="Search shows&hellip;" autocomplete="off" enterkeyhint="search"><div id="suggest" class="suggest" hidden></div></div>
    <div class="controls"><label class="pill"><input type="checkbox" id="simSameGenre"> Same genre only</label></div>
    <div id="profile"><div class="empty">Search any show to see its taste profile, execution score, and nearest neighbours.</div></div>
  </section>
  <section id="panel-foryou" class="panel">
    <div class="search"><input id="reactInput" type="search" placeholder="Add a show you&rsquo;ve seen&hellip;" autocomplete="off" enterkeyhint="search"><div id="suggest2" class="suggest" hidden></div></div>
    <div id="chips"></div>
    <div class="controls">
      <select id="recGenre"></select>
      <label class="pill"><input type="checkbox" id="sortQ"> Sort by quality</label>
      <label class="pill"><input type="checkbox" id="wlOnly"> Watchlist only</label>
    </div>
    <div class="row"><button id="recBtn" class="primary">Recommend</button><button id="clearBtn" class="ghost">Clear</button></div>
    <div id="recs"></div>
  </section>
  <section id="panel-browse" class="panel">
    <div class="hint">Dial in the profile you&rsquo;re in the mood for &mdash; results update as you drag.</div>
    <div id="filters"></div>
    <div class="row"><button id="resetFilter" class="ghost">Reset all</button></div>
    <div id="filterResults"></div>
  </section>
  <section id="panel-about" class="panel">
    <div class="ab">
      <h3>What this is</h3>
      <p>Show Type <b>describes</b> television instead of ranking it. Every show here is
        scored 0&ndash;10 on the same eight axes &mdash; how propulsive it is, how big its
        world is, how much it asks of you &mdash; which turns each show into a point in an
        eight-dimensional space. Shows that sit near each other <i>feel</i> alike, even when
        they share no genre.</p>
      <p class="mut">That&rsquo;s the useful part: &ldquo;more like this&rdquo; usually means
        more of a certain texture, not more of a category. A crime drama and a hospital drama
        can be near-neighbours here.</p>
    </div>
    <div class="ab">
      <h3>Getting started</h3>
      <ol class="steps">
        <li><b>Explore</b> &mdash; search a show you already know. You&rsquo;ll see its
          profile across the eight axes, why it scored that way, and its nearest neighbours.
          Start with something you love and see who its neighbours are.</li>
        <li><b>For You</b> &mdash; add a handful of shows and mark each one loved, liked,
          never interested, or started &amp; stopped. Recommendations are drawn from the
          centre of what you liked, pushed away from what you didn&rsquo;t. Five or six
          shows is enough to get something useful.</li>
        <li><b>Browse</b> &mdash; skip the ratings and dial in a profile directly. Drag the
          sliders to say what you&rsquo;re in the mood for &mdash; low propulsion, high
          verisimilitude, whatever &mdash; and the catalogue narrows as you go.</li>
      </ol>
    </div>
    <div class="ab">
      <h3>The eight axes</h3>
      <p class="mut">Each is scored 0&ndash;10. None of them means &ldquo;good&rdquo; &mdash;
        they only say where a show sits.</p>
      <div id="axdefs"></div>
    </div>
    <div class="ab">
      <h3>Good to know</h3>
      <ul class="facts">
        <li><b>The axes are descriptive, not evaluative.</b> A 2 is not worse than a 9. A
          show scoring 2 on Density isn&rsquo;t dumb, it just doesn&rsquo;t demand much;
          a 10 isn&rsquo;t smart, it just won&rsquo;t hold your hand.</li>
        <li><b>Quality is tracked separately</b>, as the execution score &mdash; the
          <span class="qb">Q</span> on a row, or <i>Execution n/10</i> on a show. That
          one <i>is</i> a judgement; the eight axes are not.</li>
        <li><b>&Delta; is distance</b> in the eight-axis space. Smaller means a closer
          match to the show or profile you started from.</li>
        <li><b>Nothing leaves your browser.</b> Your ratings, reasons, and watchlist are
          stored on this device only. No account, no upload, no tracking &mdash; and
          clearing your browser data clears them.</li>
        <li><b>The scores are model-generated.</b> Every show was characterised by Claude
          against a written rubric, not by critics or viewer votes. Treat them as a
          consistent reading rather than a verdict &mdash; and expect the occasional
          obscure show to be read poorly.</li>
      </ul>
    </div>
    <div class="ab">
      <h3>Open source</h3>
      <p class="mut">The code, the scoring rubric, and the full dataset are on GitHub,
        MIT-licensed &mdash;
        <a href="https://github.com/roskosevan-code/showtype" target="_blank" rel="noopener">github.com/roskosevan-code/showtype</a>.
        If an axis reads wrong to you, the rubric is the thing to argue with.</p>
    </div>
  </section>
</main>
<div id="scrim" hidden></div>
<div id="sheet" role="dialog" aria-modal="true" hidden><div class="grab"></div><div id="sheetBody"></div></div>
"""

# Data access for the served UI: thin async adapters over the JSON API. The
# offline build replaces this object with local computation over a DATA blob;
# both expose the same five methods consumed by UI_JS.
SERVED_ENGINE_JS = """
const j=async u=>{const r=await fetch(u);return r.json();};
const ENGINE={
  meta:async()=>{const m=await j('/api/meta');return{axes:m.axes,genres:m.genres||[],titles:m.shows};},
  show:async t=>{const d=await j('/api/show?title='+encodeURIComponent(t));
    if(d.error)throw new Error(d.error); d.values=d.scores.map(s=>s.value); return d;},
  similar:async(t,n,sameGenre)=>j('/api/similar?n='+n+'&title='+encodeURIComponent(t)+(sameGenre?'&same_genre=1':'')),
  recommend:async o=>{const p=new URLSearchParams({n:String(o.n||12)});
    if(o.loved.length)p.set('loved',o.loved.join('|'));
    if(o.liked.length)p.set('liked',o.liked.join('|'));
    if(o.nope.length)p.set('nope',o.nope.join('|'));
    if(o.genre)p.set('genre',o.genre);
    if(o.seen.length)p.set('seen',o.seen.join('|'));
    if(o.only)p.set('only',o.only.join('|'));
    for(const a in o.push)p.append('push',a+','+o.push[a]);
    const d=await j('/api/recommend?'+p.toString());
    if(d.error)throw new Error(d.error);
    return{disliked:(d.disliked||[]).length,centroid:d.centroid,recommendations:d.recommendations};},
  query:async fs=>j('/api/query?'+fs.map(s=>`f=${s.id},${s.min},${s.max}`).join('&')),
};
"""

UI_JS = """
let AXES=[],GENRES=[],TITLES=[];
// Single affinity ranking, best -> worst. loved/liked are positives; nope
// (never interested) is a blunt negative; dropped (started & stopped) is a
// negative that also elicits reason codes -> masked axis pushes.
const RX=[['loved','\\u2764\\ufe0f','Loved'],['liked','\\ud83d\\udc4d','Liked'],['nope','\\ud83d\\ude45','Never interested'],['dropped','\\u23f9\\ufe0f','Started & stopped']];
const WATCH=[['watchlist','\\ud83d\\udd16','Watchlist'],['seen','\\ud83d\\udc41','Seen']];
// negative-only complaints -> per-axis push (axis id -> sign; +1 want more, -1 want less)
const COMPLAINTS=[['slow','Too slow',{1:1}],['dense','Hard to follow',{7:-1}],['cold',"Couldn't connect",{4:1}],['tryhard','Too try-hard',{5:-1}],['unreal',"Didn't buy it",{6:1}],['corny','Too corny',{8:-1,6:1}]];
const PUSH_STEP=1.5,PUSH_CAP=3;
// Plain-language gloss for the About tab, in rubric order 1-8. Axis *names* come
// from the data (AXES) so they can't drift; these are the reader-facing
// paraphrases of docs/rubric.md, which stays the source of truth for scoring.
const AXIS_HELP=[
  ['Forward momentum &mdash; how much each scene creates the conditions for the next. Not speed or action: a slow, talky show can be intensely propulsive, and a busy one can idle.',
   'circles and withholds','&ldquo;one more episode&rdquo;'],
  ['The size of the canvas &mdash; how much world there is, measured in places, years, or layers of society. Whichever is largest wins.',
   'one place, one small group','continents or centuries'],
  ['How far a system or institution is the show&rsquo;s real subject, rather than a backdrop. The test: swap the institution for another one &mdash; is it still the same story?',
   'institutions are scenery','the machine is the subject'],
  ['How far inside a consciousness the show goes, as against observing behaviour from the outside. The vertical complement to scope.',
   'watched from outside','staged inside a mind'],
  ['How strong and recognisable the authorial hand is &mdash; loud or quiet. Would you know it blind? This is formal and visual boldness, not tone.',
   'craft kept invisible','unmistakable on sight'],
  ['How authentic, granular, and lived-in the world feels &mdash; whether the writers did the homework. Independent of how stylised the show is.',
   'mythologised, glamorised','feels reported'],
  ['How much the show asks of you per minute, and how willing it is to withhold exposition and trust you to keep up.',
   'recaps and hand-holding','track it yourself'],
  ['Tonal pitch &mdash; how loudly the emotions are played. Not how high the stakes are: a life-or-death show played cool and flat is low register.',
   'restrained, deadpan','operatic, maximalist'],
];
// One-time key migration from the old 'ti-' (Taste Index) prefix to 'st-'. The
// old keys are left in place so a downgrade doesn't lose anything; drop this
// block once nobody is coming from a pre-rename page.
(function(){for(const k of ['reactions','watch','reasons','tab']){
  const old=localStorage.getItem('ti-'+k);
  if(old!==null&&localStorage.getItem('st-'+k)===null)localStorage.setItem('st-'+k,old);
}})();
let reactions=JSON.parse(localStorage.getItem('st-reactions')||'{}');
let watch=JSON.parse(localStorage.getItem('st-watch')||'{}');
let reasons=JSON.parse(localStorage.getItem('st-reasons')||'{}');
const saveReactions=()=>localStorage.setItem('st-reactions',JSON.stringify(reactions));
const saveWatch=()=>localStorage.setItem('st-watch',JSON.stringify(watch));
const saveReasons=()=>localStorage.setItem('st-reasons',JSON.stringify(reasons));
// Migrate the old model: bounced watch-state -> dropped reaction; a reasoned
// nope -> dropped; drop the retired 'fine'.
(function(){let m=false;
  for(const t in watch){ if(watch[t]==='dropped'){ if(!reactions[t]) reactions[t]='dropped'; delete watch[t]; m=true; } }
  for(const t in reactions){ if(reactions[t]==='nope'&&(reasons[t]||[]).length){ reactions[t]='dropped'; m=true; } else if(reactions[t]==='fine'){ delete reactions[t]; m=true; } }
  if(m){ saveReactions(); saveWatch(); }})();
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const enc=encodeURIComponent,dec=decodeURIComponent;

/* ---------- shared renderers ---------- */
function bars(values){
  return '<div class="axes">'+AXES.map((a,i)=>{const v=values[i];
    return `<div class="ax"><span class="lbl">${a.name}</span><span class="bar"><span style="width:${v*10}%"></span></span><span class="v">${v}</span></div>`;}).join('')+'</div>';
}
function whyText(v,ref){
  const d=AXES.map((a,i)=>({n:a.name,gap:Math.abs(v[i]-ref[i]),v:v[i],r:Math.round(ref[i])}));
  const near=d.slice().sort((a,b)=>a.gap-b.gap).slice(0,3).map(x=>x.n);
  const far=d.slice().sort((a,b)=>b.gap-a.gap)[0];
  let s='Aligns on <b>'+near.join('</b>, <b>')+'</b>';
  if(far.gap>=3)s+=' &middot; differs on <b>'+far.n+'</b> ('+far.v+' vs ~'+far.r+')';
  return s;
}
function stateIcons(t){
  let s='';const r=reactions[t];if(r)s+=RX.find(x=>x[0]===r)[1];
  const w=watch[t];if(w)s+=WATCH.find(x=>x[0]===w)[1];return s;
}
function rowItem(it,ref){
  const why=ref?whyText(it.values,ref):'';
  const sub=(it.genres||[]).slice(0,3).map(g=>`<span>${esc(g)}</span>`);
  if(it.quality!=null)sub.push(`<span class="qb">Q${it.quality}</span>`);
  if(it.distance!=null)sub.push(`<span class="dist">\\u0394 ${it.distance}</span>`);
  return `<li><button class="item" data-t="${enc(it.title)}" data-why="${enc(why)}">`+
    `<span class="imain"><span class="ttl">${esc(it.title)}</span><span class="isub">${sub.join('')}</span></span>`+
    `<span class="state">${stateIcons(it.title)}</span><span class="chev">\\u203a</span></button></li>`;
}
function neighborList(items,ref){
  if(!items.length)return '<div class="hint">No matches.</div>';
  return '<ul class="list">'+items.map(it=>rowItem(it,ref)).join('')+'</ul>';
}
function segRX(t){const cur=reactions[t];
  return '<div class="seg">'+RX.map(([r,em,lbl])=>`<button class="segb${cur===r?' on':''}" data-rx="${r}" data-t="${enc(t)}"><span class="em">${em}</span>${lbl}</button>`).join('')+'</div>';}
function segWatch(t){const cur=watch[t];
  return '<div class="seg">'+WATCH.map(([w,em,lbl])=>`<button class="segb${cur===w?' on':''}" data-wx="${w}" data-t="${enc(t)}"><span class="em">${em}</span>${lbl}</button>`).join('')+'</div>';}
function reasonBlock(t){
  if(reactions[t]!=='dropped')return '';
  const cur=reasons[t]||[];
  return `<div class="rsnlbl">Why didn&rsquo;t it land? <span style="color:var(--faint)">(tunes your recs)</span></div><div class="rsn">`+
    COMPLAINTS.map(([k,lbl])=>`<button class="rsnb${cur.includes(k)?' on':''}" data-rsn="${k}" data-t="${enc(t)}">${lbl}</button>`).join('')+'</div>';
}

/* ---------- tabs ---------- */
function setTab(id){
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.tab===id));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id==='panel-'+id));
  localStorage.setItem('st-tab',id);
  if(id==='foryou')refreshForYou();
  window.scrollTo({top:0});
}

/* ---------- bottom sheet ---------- */
let sheetData=null,sheetWhy='';
function sheetHTML(d,why){
  const t=d.title;
  const badges=(d.genres||[]).map(g=>`<span class="badge">${esc(g)}</span>`).join('')+
    (d.quality!=null?`<span class="badge q">Execution ${d.quality}/10</span>`:'');
  const meta=[];if(d.episodes)meta.push('&approx;'+d.episodes+' episodes');
  if(d.seasons)meta.push(d.seasons+' season'+(d.seasons===1?'':'s'));
  let h=`<div class="shead"><h3>${esc(t)}</h3><button class="x" data-close>\\u2715</button></div><div class="badges">${badges}</div>`;
  if(d.summary)h+=`<div class="summary">${d.summary}</div>`;
  if(meta.length)h+=`<div class="metaline">${meta.join(' &middot; ')}</div>`;
  if(why)h+=`<div class="whybox">${why}</div>`;
  h+=`<div class="sec"><h4>Your take</h4>${segRX(t)}${reasonBlock(t)}</div>`;
  h+=`<div class="sec"><h4>Watch status</h4>${segWatch(t)}</div>`;
  h+=`<div class="sec"><h4>Taste profile</h4>${bars(d.values)}</div>`;
  h+=`<button class="ghost wide" data-full="${enc(t)}">Full profile &amp; similar shows \\u2192</button>`;
  return h;
}
async function openSheet(title,why){
  let d;try{d=await ENGINE.show(title);}catch(e){return;}
  sheetData=d;sheetWhy=why||'';
  $('#sheetBody').innerHTML=sheetHTML(d,sheetWhy);
  $('#scrim').hidden=false;$('#sheet').hidden=false;$('#sheet').scrollTop=0;
  requestAnimationFrame(()=>{$('#scrim').classList.add('on');$('#sheet').classList.add('on');});
  document.body.style.overflow='hidden';
}
function closeSheet(){
  if(!sheetData)return;
  sheetData=null;
  $('#scrim').classList.remove('on');$('#sheet').classList.remove('on');
  document.body.style.overflow='';
  setTimeout(()=>{$('#scrim').hidden=true;$('#sheet').hidden=true;},250);
}

/* ---------- explore ---------- */
let curShow=null,simHTML='';
function renderProfile(){
  const d=curShow;if(!d)return;
  const badges=(d.genres||[]).map(g=>`<span class="badge">${esc(g)}</span>`).join('');
  const meta=[];if(d.episodes)meta.push('&approx;'+d.episodes+' episodes');
  if(d.seasons)meta.push(d.seasons+' season'+(d.seasons===1?'':'s'));
  let h=`<div class="hero"><h3>${esc(d.title)}</h3><div class="badges">${badges}</div>`;
  if(d.summary)h+=`<div class="summary">${d.summary}</div>`;
  if(meta.length)h+=`<div class="metaline">${meta.join(' &middot; ')}</div>`;
  h+=`<div class="sec"><h4>Your take</h4>${segRX(d.title)}${reasonBlock(d.title)}</div>`;
  h+=`<div class="sec"><h4>Watch status</h4>${segWatch(d.title)}</div>`;
  h+=`<div class="sec"><h4>Taste profile</h4>${bars(d.values)}</div>`;
  if(d.quality!=null)h+=`<div class="qblock"><b>Execution ${d.quality}/10</b>${d.quality_reason?' &middot; '+d.quality_reason:''}</div>`;
  h+=`<details class="just"><summary>Why these scores</summary>`+
    d.scores.map(s=>`<div class="jrow"><b>${s.axis} ${s.value}</b> &middot; ${s.justification} <i>(${s.confidence})</i></div>`).join('')+`</details>`;
  h+=`</div><div id="simwrap">${simHTML}</div>`;
  $('#profile').innerHTML=h;
}
async function loadShow(title,switchTab){
  if(switchTab)setTab('explore');
  $('#pick').value=title;
  let d;try{d=await ENGINE.show(title);}catch(e){$('#profile').innerHTML=`<div class="err">${esc(e.message)}</div>`;return;}
  curShow=d;simHTML='';renderProfile();
  const sim=await ENGINE.similar(title,8,$('#simSameGenre').checked);
  simHTML='<div class="lh">Nearest in taste-space</div>'+neighborList(sim.neighbors,sim.values);
  const w=$('#simwrap');if(w&&curShow&&curShow.title===title)w.innerHTML=simHTML;
}

/* ---------- for you ---------- */
const GROUPS=[['loved','\\u2764\\ufe0f Loved'],['liked','\\ud83d\\udc4d Liked'],['nope','\\ud83d\\ude45 Never interested'],['dropped','\\u23f9\\ufe0f Started & stopped']];
function renderChips(){
  const byR={loved:[],liked:[],nope:[],dropped:[]};
  for(const t of Object.keys(reactions).sort((a,b)=>a.localeCompare(b)))
    if(byR[reactions[t]])byR[reactions[t]].push(t);
  const wl=Object.keys(watch).filter(t=>watch[t]==='watchlist').length;
  const seen=Object.keys(watch).filter(t=>watch[t]==='seen').length;
  let h='';
  if(wl||seen){const bits=[];if(wl)bits.push('\\ud83d\\udd16 '+wl+' on watchlist');if(seen)bits.push('\\ud83d\\udc41 '+seen+' seen');
    h+=`<div class="wline">${bits.join(' &middot; ')}</div>`;}
  const any=GROUPS.some(([r])=>byR[r].length);
  if(!any){$('#chips').innerHTML=h+'<div class="empty">Search for shows you&rsquo;ve watched and rank them \\u2014 personalised recommendations appear here.</div>';return;}
  for(const [r,lbl] of GROUPS){
    if(!byR[r].length)continue;
    h+=`<div class="glab">${lbl} (${byR[r].length})</div><div class="chips">`+byR[r].map(t=>{
      const e=enc(t);let why='';
      if(r==='dropped'){const n=(reasons[t]||[]).length;why=` <span class="why">${n?'why\\u00b7'+n:'why?'}</span>`;}
      return `<span class="chip"><button class="nm" data-open="${e}"><span class="tx">${esc(t)}</span>${why}</button><button class="rm" data-rm="${e}" title="Remove">\\u2715</button></span>`;
    }).join('')+'</div>';
  }
  $('#chips').innerHTML=h;
}
function collectPushes(){
  // Aggregate complaint pushes across reasoned started-&-stopped shows; cap per axis.
  const push={};
  const add=t=>(reasons[t]||[]).forEach(k=>{const c=COMPLAINTS.find(x=>x[0]===k);
    if(c)for(const a in c[2])push[a]=(push[a]||0)+c[2][a]*PUSH_STEP;});
  for(const t in reactions)if(reactions[t]==='dropped'&&(reasons[t]||[]).length)add(t);
  for(const a in push)push[a]=Math.max(-PUSH_CAP,Math.min(PUSH_CAP,push[a]));
  return push;
}
async function recommend(){
  const groups={loved:[],liked:[],nope:[],dropped:[]};
  for(const t in reactions)if(groups[reactions[t]])groups[reactions[t]].push(t);
  if(!groups.loved.length&&!groups.liked.length){$('#recs').innerHTML='';return;}
  // Never-interested and unreasoned started&stopped push away bluntly; reasoned
  // started&stopped steers via masked axis pushes and is just excluded via `seen`.
  const seen=new Set(Object.keys(watch).filter(t=>watch[t]==='seen'));
  const blunt=[...groups.nope];
  groups.dropped.forEach(t=>{(reasons[t]||[]).length?seen.add(t):blunt.push(t);});
  const wlOnly=$('#wlOnly').checked;
  const wl=Object.keys(watch).filter(t=>watch[t]==='watchlist');
  if(wlOnly&&!wl.length){$('#recs').innerHTML='<div class="hint">Nothing on your watchlist yet \\u2014 mark shows with \\ud83d\\udd16.</div>';return;}
  const push=collectPushes(),g=$('#recGenre').value;
  let d;try{
    d=await ENGINE.recommend({loved:groups.loved,liked:groups.liked,nope:blunt,
      seen:[...seen],only:wlOnly?wl:null,genre:g,push,n:12});
  }catch(e){$('#recs').innerHTML=`<div class="err">${esc(e.message)}</div>`;return;}
  const bits=[];if(g)bits.push(esc(g));if(wlOnly)bits.push('from watchlist');
  if(d.disliked)bits.push('away from '+d.disliked+' you rejected');
  if(Object.keys(push).length)bits.push('tuned to your reasons');
  let recs=d.recommendations;
  if($('#sortQ').checked){bits.push('by quality');recs=recs.slice().sort((a,b)=>(b.quality??-1)-(a.quality??-1));}
  $('#recs').innerHTML=`<div class="lh">For you${bits.length?' <span class="mut">&middot; '+bits.join(' &middot; ')+'</span>':''}</div>`+neighborList(recs,d.centroid);
}
function refreshForYou(){renderChips();recommend();}

/* ---------- browse ---------- */
function buildFilters(){
  $('#filters').innerHTML=AXES.map(a=>
    `<div class="frow" data-axis="${a.id}"><div class="fhead"><span>${a.name}</span><span class="frd" id="frd-${a.id}">any</span></div>`+
    `<div class="fr2"><span>min</span><input type="range" min="0" max="10" value="0" data-kind="min" aria-label="${a.name} min"></div>`+
    `<div class="fr2"><span>max</span><input type="range" min="0" max="10" value="10" data-kind="max" aria-label="${a.name} max"></div></div>`).join('');
}
function syncPair(el){
  const row=el.closest('.frow');
  const mn=row.querySelector('[data-kind=min]'),mx=row.querySelector('[data-kind=max]');
  if(+mn.value>+mx.value){if(el.dataset.kind==='min')mx.value=mn.value;else mn.value=mx.value;}
  const rd=$('#frd-'+row.dataset.axis),active=+mn.value>0||+mx.value<10;
  rd.textContent=active?mn.value+'\\u2013'+mx.value:'any';
  rd.classList.toggle('set',active);
}
async function runQuery(){
  const fs=[...document.querySelectorAll('.frow')].map(r=>({
    id:+r.dataset.axis,min:+r.querySelector('[data-kind=min]').value,max:+r.querySelector('[data-kind=max]').value
  })).filter(s=>s.min>0||s.max<10);
  const d=await ENGINE.query(fs);
  let h=`<div class="lh">${d.count} show${d.count===1?'':'s'} match${fs.length?'':' <span class="mut">&middot; no filter</span>'}</div>`+
    '<ul class="list">'+d.matches.map(m=>rowItem(m)).join('')+'</ul>';
  if(d.count>d.matches.length)h+=`<div class="hint">showing first ${d.matches.length}</div>`;
  $('#filterResults').innerHTML=h;
}

/* ---------- about ---------- */
function renderAxisDefs(){
  $('#axdefs').innerHTML=AXES.map((a,i)=>{
    const [desc,lo,hi]=AXIS_HELP[i]||['','',''];
    return `<div class="axd"><div class="an">${i+1}. ${esc(a.name)} <i>${esc(a.code)}</i></div>`+
      `<div class="ad">${desc}</div>`+
      `<div class="poles"><span>0 &middot; ${lo}</span><span class="hi">${hi} &middot; 10</span></div></div>`;
  }).join('');
}

/* ---------- state changes ---------- */
function refreshUI(t){
  const e=enc(t);
  document.querySelectorAll(`.item[data-t="${e}"] .state`).forEach(el=>{el.textContent=stateIcons(t);});
  if(curShow&&curShow.title===t)renderProfile();
  renderChips();
  if(sheetData&&sheetData.title===t)$('#sheetBody').innerHTML=sheetHTML(sheetData,sheetWhy);
  if($('#recs').innerHTML)recommend();
}
function setReaction(t,r){
  if(reactions[t]===r)delete reactions[t];else reactions[t]=r;
  saveReactions();refreshUI(t);
}
function setWatch(t,w){
  if(watch[t]===w)delete watch[t];else watch[t]=w;
  saveWatch();refreshUI(t);
}
function toggleReason(t,k){
  const cur=reasons[t]||[];
  reasons[t]=cur.includes(k)?cur.filter(x=>x!==k):[...cur,k];
  if(!reasons[t].length)delete reasons[t];
  saveReasons();refreshUI(t);
}

/* ---------- search suggest ---------- */
function attachSuggest(inpSel,boxSel,onPick){
  const inp=$(inpSel),box=$(boxSel);
  inp.addEventListener('input',()=>{
    const q=inp.value.trim().toLowerCase();
    if(!q){box.hidden=true;return;}
    const st=[],inc=[];
    for(const t of TITLES){const l=t.toLowerCase();
      if(l.startsWith(q)){st.push(t);if(st.length>=10)break;}
      else if(inc.length<10&&l.includes(q))inc.push(t);}
    const m=st.concat(inc).slice(0,10);
    box.innerHTML=m.length?m.map(t=>`<button data-s="${enc(t)}">${esc(t)}</button>`).join('')
      :'<button disabled style="color:var(--faint)">No matches</button>';
    box.hidden=false;
  });
  inp.addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      const q=inp.value.trim().toLowerCase();
      const hit=TITLES.find(t=>t.toLowerCase()===q)||TITLES.find(t=>t.toLowerCase().startsWith(q));
      if(hit){onPick(hit);box.hidden=true;inp.blur();}
    }else if(e.key==='Escape'){box.hidden=true;}
  });
  box.addEventListener('click',e=>{
    const b=e.target.closest('button[data-s]');
    if(b){onPick(dec(b.dataset.s));box.hidden=true;inp.blur();}
  });
}

/* ---------- events ---------- */
document.addEventListener('pointerdown',e=>{
  if(!e.target.closest('.search'))document.querySelectorAll('.suggest').forEach(b=>{b.hidden=true;});
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeSheet();});
document.addEventListener('click',e=>{
  const tb=e.target.closest('.tab');if(tb){setTab(tb.dataset.tab);return;}
  if(e.target.closest('[data-close]')||e.target.id==='scrim'){closeSheet();return;}
  const rm=e.target.closest('[data-rm]');if(rm){const t=dec(rm.dataset.rm);
    delete reactions[t];delete reasons[t];saveReactions();saveReasons();refreshUI(t);return;}
  const rx=e.target.closest('.segb[data-rx]');if(rx){setReaction(dec(rx.dataset.t),rx.dataset.rx);return;}
  const wx=e.target.closest('.segb[data-wx]');if(wx){setWatch(dec(wx.dataset.t),wx.dataset.wx);return;}
  const rb=e.target.closest('.rsnb');if(rb){toggleReason(dec(rb.dataset.t),rb.dataset.rsn);return;}
  const fl=e.target.closest('[data-full]');if(fl){const t=dec(fl.dataset.full);closeSheet();loadShow(t,true);return;}
  const op=e.target.closest('[data-open]');if(op){openSheet(dec(op.dataset.open));return;}
  const it=e.target.closest('.item');if(it){openSheet(dec(it.dataset.t),dec(it.dataset.why||''));return;}
});
document.addEventListener('change',e=>{
  const p=e.target.closest('.pill');
  if(p&&e.target.type==='checkbox')p.classList.toggle('on',e.target.checked);
});
$('#simSameGenre').addEventListener('change',()=>{if(curShow)loadShow(curShow.title);});
$('#recGenre').addEventListener('change',recommend);
$('#sortQ').addEventListener('change',()=>{if($('#recs').innerHTML)recommend();});
$('#wlOnly').addEventListener('change',()=>{recommend();});
$('#recBtn').addEventListener('click',recommend);
$('#clearBtn').addEventListener('click',()=>{
  if(!Object.keys(reactions).length||confirm('Clear all your rankings and reasons?')){
    reactions={};reasons={};saveReactions();saveReasons();
    renderChips();$('#recs').innerHTML='';if(curShow)renderProfile();
  }
});
let qTimer;
$('#filters').addEventListener('input',e=>{
  if(e.target.type==='range'){syncPair(e.target);clearTimeout(qTimer);qTimer=setTimeout(runQuery,180);}
});
$('#resetFilter').addEventListener('click',()=>{
  document.querySelectorAll('.frow').forEach(r=>{
    r.querySelector('[data-kind=min]').value=0;r.querySelector('[data-kind=max]').value=10;
    const rd=$('#frd-'+r.dataset.axis);rd.textContent='any';rd.classList.remove('set');
  });
  runQuery();
});

/* ---------- init ---------- */
(async()=>{
  const m=await ENGINE.meta();
  AXES=m.axes;GENRES=m.genres;TITLES=m.titles.slice().sort((a,b)=>a.localeCompare(b));
  $('#count').textContent=TITLES.length.toLocaleString()+' shows';
  $('#pick').placeholder='Search '+TITLES.length.toLocaleString()+' shows\\u2026';
  $('#recGenre').innerHTML='<option value="">All genres</option>'+GENRES.map(g=>`<option>${esc(g)}</option>`).join('');
  buildFilters();renderAxisDefs();renderChips();runQuery();
  attachSuggest('#pick','#suggest',t=>loadShow(t));
  attachSuggest('#reactInput','#suggest2',t=>{$('#reactInput').value='';openSheet(t);});
  setTab(localStorage.getItem('st-tab')||'explore');
})();
"""

PAGE = PAGE_HEAD + "<script>\n" + SERVED_ENGINE_JS + UI_JS + "</script>\n</body></html>"
