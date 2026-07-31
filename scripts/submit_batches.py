#!/usr/bin/env python3
"""Submit the scores/genres/quality batches for a title file and RECORD their IDs.

Unlike score-batch / classify_genres.py / build_quality.py (which submit, block-poll,
and save in one process), this only *submits* and writes the batch IDs to a JSON file,
so a dead session never loses them. Poll separately and fetch with fetch_batches.py.

    ANTHROPIC_API_KEY=... python3 scripts/submit_batches.py \
        --file scripts/catalog-shows-4.txt --out docs/round4-main-batches.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import classify_genres as G  # noqa: E402
import build_quality as Q  # noqa: E402
from showtype import db  # noqa: E402
from showtype.cli import _collect_titles, load_rubric, DEFAULT_RUBRIC  # noqa: E402
from showtype.scorer import build_batch_params  # noqa: E402

GENRES_CSV = REPO / "docs" / "genres.csv"
QUALITY_CSV = REPO / "docs" / "quality.csv"


def _submit(client, requests, label):
    b = client.messages.batches.create(requests=requests)
    print(f"{label:8} submitted {b.id} ({len(requests)} requests)")
    return b.id


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--out", required=True, help="where to record the batch IDs (JSON)")
    ap.add_argument("--model", default="claude-opus-4-8")
    args = ap.parse_args()

    titles = _collect_titles([], args.file)
    client = anthropic.Anthropic()
    rec = {"file": args.file, "model": args.model, "batches": {}}

    # SCORES — skip titles already scored in the DB.
    rubric_text, _ = load_rubric(DEFAULT_RUBRIC)
    conn = db.connect(db.DEFAULT_DB_PATH)
    axis_names = [r["name"] for r in db.get_axes(conn)]
    in_db = {r["title"] for r in conn.execute("SELECT title FROM show")}
    s_titles = [t for t in titles if t not in in_db]
    if s_titles:
        reqs = [Request(custom_id=f"sh{i:04d}",
                        params=MessageCreateParamsNonStreaming(
                            **build_batch_params(t, rubric_text, axis_names, model=args.model)))
                for i, t in enumerate(s_titles)]
        rec["batches"]["scores"] = _submit(client, reqs, "SCORES")
    print(f"  scores: {len(s_titles)}/{len(titles)} new (skipped {len(titles)-len(s_titles)})")

    # GENRES — skip titles already in genres.csv.
    g_have = {r["show"] for r in csv.DictReader(open(GENRES_CSV, encoding="utf-8"))}
    g_titles = [t for t in titles if t not in g_have]
    if g_titles:
        reqs = [Request(custom_id=f"g{i:04d}",
                        params=MessageCreateParamsNonStreaming(**G.params(t)))
                for i, t in enumerate(g_titles)]
        rec["batches"]["genres"] = _submit(client, reqs, "GENRES")
    print(f"  genres: {len(g_titles)}/{len(titles)} new (skipped {len(titles)-len(g_titles)})")

    # QUALITY — skip titles already in quality.csv.
    q_have = {r["show"] for r in csv.DictReader(open(QUALITY_CSV, encoding="utf-8"))}
    q_titles = [t for t in titles if t not in q_have]
    if q_titles:
        reqs = [Request(custom_id=f"q{i:04d}",
                        params=MessageCreateParamsNonStreaming(**Q.params(t)))
                for i, t in enumerate(q_titles)]
        rec["batches"]["quality"] = _submit(client, reqs, "QUALITY")
    print(f"  quality: {len(q_titles)}/{len(titles)} new (skipped {len(titles)-len(q_titles)})")

    Path(args.out).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"\nRecorded batch IDs -> {args.out}")
    print(json.dumps(rec["batches"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
