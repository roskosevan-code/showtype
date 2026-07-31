#!/usr/bin/env python3
"""Retrieve completed Batches-API results by ID and save them.

Recovery / resume tool for the scoring pipeline. The normal scripts submit + poll
+ save in one process; if that process dies (reboot, killed session) before its
batch ends, the results still live on Anthropic's servers (~29 days). This fetches
a batch by ID and saves it. **Retrieval only** — it never generates, so it never
re-bills.

Robustness: instead of trusting the positional custom_ids (which only line up if
nothing was partially saved), each result is matched by the show name the model
echoes back, normalized against the canonical titles in --file. All saves are
idempotent, so running this is safe even if the original poller already saved some.

    export ANTHROPIC_API_KEY=...
    python3 scripts/fetch_batches.py \
        --file scripts/catalog-shows-4-val.txt \
        --scores msgbatch_xxx --genres msgbatch_yyy --quality msgbatch_zzz
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import anthropic  # noqa: E402

from showtype import db  # noqa: E402
from showtype.cli import _collect_titles, _normalize  # noqa: E402
from showtype.scorer import parse_message_scores  # noqa: E402

GENRES_CSV = REPO / "docs" / "genres.csv"
QUALITY_CSV = REPO / "docs" / "quality.csv"
# Keep in sync with scripts/classify_genres.py
VOCAB = ["Crime", "Thriller", "Drama", "Political", "Sci-Fi", "Fantasy",
         "Comedy", "Horror", "War", "Western", "Historical", "Mystery"]


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _canon_map(file: str) -> dict[str, str]:
    """normalized title -> canonical title, from the input file."""
    return {_norm_title(t): t for t in _collect_titles([], file)}


def _resolve(show: str, canon: dict[str, str]) -> str:
    """Map a model-echoed show name to the canonical catalog title."""
    return canon.get(_norm_title(show), show)


def _text(message) -> str | None:
    return next((b.text for b in message.content if b.type == "text"), None)


def _ensure_ended(client, bid: str, label: str):
    b = client.messages.batches.retrieve(bid)
    if b.processing_status != "ended":
        rc = b.request_counts
        print(f"  {label} {bid}: NOT ended (status={b.processing_status}, "
              f"processing={rc.processing} ok={rc.succeeded}) — skipping.", file=sys.stderr)
        return False
    return True


def fetch_scores(client, bid: str, file: str, db_path: str, model: str) -> None:
    if not _ensure_ended(client, bid, "SCORES"):
        return
    conn = db.connect(db_path)
    axis_rows = db.get_axes(conn)
    if not axis_rows:
        print("  SCORES: no axes seeded (run init-db / db-load first).", file=sys.stderr)
        return
    axis_id_by_norm = {_normalize(r["name"]): int(r["id"]) for r in axis_rows}
    canon = _canon_map(file)
    ok = fail = 0
    failed = []
    for res in client.messages.batches.results(bid):
        if res.result.type != "succeeded":
            fail += 1
            continue
        try:
            parsed = parse_message_scores(res.result.message)
            title = _resolve(parsed.show, canon)
            rows = []
            for s in parsed.scores:
                aid = axis_id_by_norm.get(_normalize(s.axis))
                if aid is not None:
                    rows.append((aid, s.value, s.confidence, s.justification, model))
            if not rows:
                raise ValueError("no valid axis rows")
            sid = db.upsert_show(conn, title)
            db.save_scores(conn, sid, rows)  # upsert on (show, axis): idempotent
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            failed.append(f"{res.custom_id} ({e})")
    print(f"SCORES  {bid}: saved {ok} shows to {db_path} ({fail} failed).")
    if failed:
        print(f"  failed: {', '.join(failed[:15])}", file=sys.stderr)


def fetch_genres(client, bid: str, file: str) -> None:
    if not _ensure_ended(client, bid, "GENRES"):
        return
    canon = _canon_map(file)
    parsed_rows: list[tuple[str, str, int]] = []
    fail = 0
    for res in client.messages.batches.results(bid):
        if res.result.type != "succeeded":
            fail += 1
            continue
        try:
            data = json.loads(_text(res.result.message))
            title = _resolve(data["show"], canon)
            gs = [g for g in data["genres"] if g in VOCAB][:3]
            if not gs:
                raise ValueError("no valid genre")
            for rank, g in enumerate(gs):
                parsed_rows.append((title, g, rank))
        except Exception:  # noqa: BLE001
            fail += 1
    # Idempotent append: skip titles already present in genres.csv right now.
    already = {r["show"] for r in csv.DictReader(open(GENRES_CSV, encoding="utf-8"))}
    new = [row for row in parsed_rows if row[0] not in already]
    with open(GENRES_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(new)
    tagged = len({t for t, _, _ in new})
    skipped = len({t for t, _, _ in parsed_rows}) - tagged
    print(f"GENRES  {bid}: appended {tagged} shows / {len(new)} rows to "
          f"docs/genres.csv ({skipped} already present, {fail} failed).")


def fetch_quality(client, bid: str, file: str) -> None:
    if not _ensure_ended(client, bid, "QUALITY"):
        return
    canon = _canon_map(file)
    fields = ["show", "quality", "quality_reason", "summary", "episodes", "seasons"]
    prior = {}
    if QUALITY_CSV.exists():
        prior = {r["show"]: r for r in csv.DictReader(open(QUALITY_CSV, encoding="utf-8"))}
    new_rows = {}
    fail = 0
    for res in client.messages.batches.results(bid):
        if res.result.type != "succeeded":
            fail += 1
            continue
        try:
            d = json.loads(_text(res.result.message))
            title = _resolve(d["show"], canon)
            new_rows[title] = {
                "show": title,
                "quality": max(0, min(10, int(d["quality"]))),
                "quality_reason": d["quality_reason"],
                "summary": d["summary"],
                "episodes": d.get("episodes"),
                "seasons": d.get("seasons"),
            }
        except Exception:  # noqa: BLE001
            fail += 1
    merged = {**prior, **new_rows}  # new wins; idempotent merge
    rows = sorted(merged.values(), key=lambda r: r["show"])
    with open(QUALITY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"QUALITY {bid}: merged {len(new_rows)} new + {len(prior)} prior = "
          f"{len(rows)} rows -> docs/quality.csv ({fail} failed).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True,
                    help="the title file the batches were submitted from")
    ap.add_argument("--scores", help="batch id for the axis-scores pass")
    ap.add_argument("--genres", help="batch id for the genre pass")
    ap.add_argument("--quality", help="batch id for the quality pass")
    ap.add_argument("--db", default=db.DEFAULT_DB_PATH)
    ap.add_argument("--model", default="claude-opus-4-8",
                    help="model id to record on saved scores")
    args = ap.parse_args()
    if not (args.scores or args.genres or args.quality):
        ap.error("pass at least one of --scores / --genres / --quality")

    client = anthropic.Anthropic()
    if args.scores:
        fetch_scores(client, args.scores, args.file, args.db, args.model)
    if args.genres:
        fetch_genres(client, args.genres, args.file)
    if args.quality:
        fetch_quality(client, args.quality, args.file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
