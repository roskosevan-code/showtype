#!/usr/bin/env python3
"""Model-judged quality + summary + episode estimates, via the Batches API.

For every catalog title, Claude returns an evaluative execution score (0-10,
distinct from the descriptive axes), a one-line justification, a spoiler-free
summary, and approximate episode/season counts (its best estimate; null when
unsure). Written to docs/quality.csv; load with `taste-index load-quality`.

    ANTHROPIC_API_KEY=... python3 scripts/build_quality.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from taste_index.cli import _collect_titles  # noqa: E402

CATALOG_CSV = REPO / "docs" / "catalog-scores.csv"
OUT = REPO / "docs" / "quality.csv"
MODEL = "claude-opus-4-8"

_nullable_int = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["show", "quality", "quality_reason", "summary", "episodes", "seasons"],
    "properties": {
        "show": {"type": "string"},
        "quality": {"type": "integer"},
        "quality_reason": {"type": "string"},
        "summary": {"type": "string"},
        "episodes": _nullable_int,
        "seasons": _nullable_int,
    },
}
SYSTEM = """\
You assess TV shows for a catalog. For each show return:
- quality: an integer 0-10 for how WELL-EXECUTED the show is — the craft of its \
writing, direction, performances, and coherence — judged on the show's own ambitions \
and INDEPENDENT of genre, popularity, or personal taste. This is evaluative (unlike a \
descriptive axis). Anchors: a landmark, near-flawless series is 9-10 (e.g. The Wire, \
Breaking Bad); a strong, well-made show is 6-7; a watchable but flawed show is 4-5; a \
poorly executed show is 0-2.
- quality_reason: one to two sentences, concrete to this show, on what drives the score.
- summary: a one-to-two sentence, spoiler-free description of the premise.
- episodes: approximate total number of episodes across all seasons — your best \
estimate. Use null if you are not reasonably sure.
- seasons: number of seasons. Use null if you are not reasonably sure.
Do not invent precise episode or season counts you are unsure of — use null instead."""


def params(title: str) -> dict:
    return {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": f"Assess the TV show: {title}"}],
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }


def all_titles() -> list[str]:
    seen: list[str] = []
    for r in csv.DictReader(open(CATALOG_CSV, encoding="utf-8")):
        if r["show"] not in seen:
            seen.append(r["show"])
    # include round-3 additions even if the catalog CSV hasn't been re-exported yet
    for f in REPO.glob("scripts/catalog-shows*.txt"):
        for t in _collect_titles([], str(f)):
            if t not in seen:
                seen.append(t)
    return seen


def main() -> int:
    titles = all_titles()
    print(f"Assessing quality for {len(titles)} shows...", file=sys.stderr)
    cid = {f"q{i:04d}": t for i, t in enumerate(titles)}
    requests = [
        Request(custom_id=c, params=MessageCreateParamsNonStreaming(**params(t)))
        for c, t in cid.items()
    ]
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    print(f"Submitted batch {batch.id} ({len(requests)} requests).", file=sys.stderr)
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(30)

    out_rows, failed = [], []
    for res in client.messages.batches.results(batch.id):
        title = cid.get(res.custom_id, res.custom_id)
        if res.result.type != "succeeded":
            failed.append(title)
            continue
        text = next((b.text for b in res.result.message.content if b.type == "text"), None)
        try:
            d = json.loads(text)
            out_rows.append({
                "show": title,
                "quality": max(0, min(10, int(d["quality"]))),
                "quality_reason": d["quality_reason"],
                "summary": d["summary"],
                "episodes": d.get("episodes"),
                "seasons": d.get("seasons"),
            })
        except Exception as e:
            failed.append(f"{title} ({e})")

    out_rows.sort(key=lambda r: r["show"])
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["show", "quality", "quality_reason", "summary",
                                          "episodes", "seasons"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {len(out_rows)} rows -> {OUT.relative_to(REPO)}.")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(map(str, failed[:20]))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
