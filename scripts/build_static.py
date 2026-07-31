#!/usr/bin/env python3
"""Build a single self-contained docs/showtype.html — no server, no deps.

Bakes every show's data into the page and provides a local-compute ENGINE with
the same interface the served UI's fetch-based engine exposes (meta / show /
similar / recommend / query). All markup, CSS, and UI logic are reused verbatim
from showtype.web (PAGE_HEAD + UI_JS), so the two builds cannot drift.

    python3 scripts/build_static.py     # -> docs/showtype.html (double-click to open)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# The offline build is always SQLite/zero-dependency. Clear DATABASE_URL for this
# process so every db.connect() (including the cli.* loaders below) uses SQLite,
# even if the caller happens to have Postgres configured.
os.environ.pop("DATABASE_URL", None)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from showtype import cli, db, space, web  # noqa: E402

DB = REPO / "showtype.db"
OUT = REPO / "docs" / "showtype.html"

# Local-compute twin of web.SERVED_ENGINE_JS, over the embedded DATA blob.
# Same five async methods; the mirrored recommend logic (weighted centroid +
# Rocchio negatives + clamped axis pushes) lives in space.recommend server-side.
STATIC_ENGINE_JS = r"""
const TITLES_ALL=Object.keys(DATA.shows).sort((a,b)=>a.localeCompare(b));
const dist=(a,b)=>Math.sqrt(a.reduce((s,v,i)=>s+(v-b[i])**2,0));
const genresOf=t=>(DATA.shows[t]?DATA.shows[t].genres:[]);
const showsWithGenre=g=>TITLES_ALL.filter(t=>genresOf(t).includes(g));
function nearestTo(vec,n,exclude,allowed){
  return TITLES_ALL.filter(t=>!exclude.has(t)&&(!allowed||allowed.has(t)))
    .map(t=>({title:t,distance:+dist(vec,DATA.shows[t].values).toFixed(2),
      genres:genresOf(t),quality:DATA.shows[t].quality,values:DATA.shows[t].values}))
    .sort((a,b)=>a.distance-b.distance).slice(0,n);
}
const ENGINE={
  meta:async()=>({axes:DATA.axes,genres:DATA.genres,titles:TITLES_ALL}),
  show:async t=>{const s=DATA.shows[t];if(!s)throw new Error('Unknown show: '+t);
    return Object.assign({title:t},s);},
  similar:async(t,n,sameGenre)=>{
    const s=DATA.shows[t];if(!s)throw new Error('Unknown show: '+t);
    let allowed=null;
    if(sameGenre){allowed=new Set();s.genres.forEach(g=>showsWithGenre(g).forEach(x=>allowed.add(x)));}
    return{title:t,genres:s.genres,values:s.values,neighbors:nearestTo(s.values,n,new Set([t]),allowed)};},
  recommend:async o=>{
    const pos=[...o.loved.map(t=>[t,2]),...o.liked.map(t=>[t,1])].filter(([t])=>DATA.shows[t]);
    const neg=o.nope.filter(t=>DATA.shows[t]);
    if(!pos.length)throw new Error('no positives');
    const wsum=pos.reduce((s,[,w])=>s+w,0);
    const cl=DATA.axes.map((_,i)=>pos.reduce((s,[t,w])=>s+w*DATA.shows[t].values[i],0)/wsum);
    let target=cl.slice();
    if(neg.length){
      const cd=DATA.axes.map((_,i)=>neg.reduce((s,t)=>s+DATA.shows[t].values[i],0)/neg.length);
      target=cl.map((v,i)=>v+0.5*(v-cd[i]));
    }
    for(const a in o.push)target[+a-1]+=o.push[a];  // axis id is 1-based
    target=target.map(v=>Math.min(10,Math.max(0,v)));
    const excl=new Set([...o.loved,...o.liked,...o.nope,...o.seen]);
    let allowed=o.genre?new Set(showsWithGenre(o.genre)):null;
    if(o.only){const wl=new Set(o.only);allowed=allowed?new Set([...allowed].filter(t=>wl.has(t))):wl;}
    return{disliked:neg.length,centroid:target.map(v=>+v.toFixed(1)),
      recommendations:nearestTo(target,o.n||12,excl,allowed)};},
  query:async fs=>{
    const matches=TITLES_ALL.filter(t=>fs.every(s=>{
      const v=DATA.shows[t].values[s.id-1];return v>=s.min&&v<=s.max;}));
    return{count:matches.length,matches:matches.slice(0,60).map(t=>({
      title:t,genres:genresOf(t),quality:DATA.shows[t].quality,values:DATA.shows[t].values}))};},
};
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
    # Always (re)load from the committed CSVs. A populated `show` table does NOT
    # imply genres/quality are current: scores can be written straight to the DB
    # (e.g. score-all / fetch_batches) while genres+quality land only in the CSVs,
    # so an early return here would ship shows with empty genres/null quality.
    # All loaders are idempotent (upsert scores/quality; tag_genres clears per show).
    db.init_schema(conn)
    ns = lambda **k: argparse.Namespace(**k)  # noqa: E731
    cli.cmd_init_db(ns(db=str(DB), rubric=str(REPO / "docs/rubric.md")))
    cli.cmd_backfill(ns(db=str(DB), csv=str(REPO / "docs/catalog-scores.csv")))
    cli.cmd_tag_genres(ns(db=str(DB), csv=str(REPO / "docs/genres.csv")))
    cli.cmd_load_quality(ns(db=str(DB), csv=str(REPO / "docs/quality.csv")))


def main() -> int:
    # Offline build is always SQLite/zero-dependency, even if DATABASE_URL is set.
    conn = db.connect(DB, force_sqlite=True)
    ensure_db(conn)
    data = build_data(conn)

    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    html = (
        web.PAGE_HEAD
        + "<script>\nconst DATA="
        + blob
        + ";\n"
        + STATIC_ENGINE_JS
        + web.UI_JS
        + "</script>\n</body></html>"
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}: {len(data['shows'])} shows, {len(html):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
