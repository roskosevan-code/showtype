#!/usr/bin/env python3
"""Classify genres for catalog shows missing them, via the Batches API.

The original 231 genres in docs/genres.csv are hand-curated; for shows added in
bulk, the model assigns 1-3 genres from the same controlled vocabulary. Results
are appended to docs/genres.csv (show,genre,rank) for titles not already tagged.

    export ANTHROPIC_API_KEY=...
    python3 scripts/classify_genres.py --file scripts/catalog-shows-3.txt
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from showtype.cli import _collect_titles  # noqa: E402

GENRES_CSV = REPO / "docs" / "genres.csv"
MODEL = "claude-opus-4-8"
VOCAB = ["Crime", "Thriller", "Drama", "Political", "Sci-Fi", "Fantasy",
         "Comedy", "Horror", "War", "Western", "Historical", "Mystery"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["show", "genres"],
    "properties": {
        "show": {"type": "string"},
        "genres": {"type": "array", "items": {"type": "string", "enum": VOCAB}},
    },
}
SYSTEM = (
    "You tag TV shows with genres for a catalog. Assign 1 to 3 genres, chosen ONLY "
    "from this exact list: " + ", ".join(VOCAB) + ". List the single most dominant "
    "genre FIRST (it becomes the primary), then up to two meaningful secondary genres. "
    "Most shows need only 1-2. Be conservative with secondaries — add one only if the "
    "show genuinely lives in two modes (e.g. a dark comedy that is also crime)."
)


def params(title: str) -> dict:
    return {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": f"Classify the TV show: {title}"}],
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--poll-interval", type=int, default=30)
    args = ap.parse_args()

    already = {r["show"] for r in csv.DictReader(open(GENRES_CSV, encoding="utf-8"))}
    titles = [t for t in _collect_titles([], args.file) if t not in already]
    if not titles:
        print("Nothing to classify.")
        return 0
    print(f"Classifying genres for {len(titles)} shows...", file=sys.stderr)

    cid_title = {f"g{i:04d}": t for i, t in enumerate(titles)}
    requests = [
        Request(custom_id=c, params=MessageCreateParamsNonStreaming(**params(t)))
        for c, t in cid_title.items()
    ]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    print(f"Submitted batch {batch.id} ({len(requests)} requests).", file=sys.stderr)

    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(args.poll_interval)

    import json
    rows: list[tuple[str, str, int]] = []
    failed: list[str] = []
    for res in client.messages.batches.results(batch.id):
        title = cid_title.get(res.custom_id, res.custom_id)
        if res.result.type != "succeeded":
            failed.append(title)
            continue
        text = next((b.text for b in res.result.message.content if b.type == "text"), None)
        try:
            data = json.loads(text)
            gs = [g for g in data["genres"] if g in VOCAB][:3]
            if not gs:
                raise ValueError("no valid genre")
        except Exception as e:
            failed.append(f"{title} ({e})")
            continue
        for rank, g in enumerate(gs):
            rows.append((title, g, rank))

    # Append to genres.csv (which already has a header).
    with open(GENRES_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    tagged = len({t for t, _, _ in rows})
    print(f"Tagged {tagged} shows ({len(rows)} rows) -> {GENRES_CSV.relative_to(REPO)}.")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:20])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
