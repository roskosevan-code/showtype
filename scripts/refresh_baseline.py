#!/usr/bin/env python3
"""Re-score the gold set under the *current* rubric -> docs/baseline-scores.csv.

This is the active diff reference: model-scored (claude-opus-4-8) under the
current docs/rubric.md, so `showtype diff` measures drift from a clean,
rubric-consistent baseline rather than the frozen Phase 0 hand-scores.

    ANTHROPIC_API_KEY=... python3 scripts/refresh_baseline.py

The gold-set titles are read from docs/phase0-scores.csv so the same 30 shows
are scored. Phase 0 artifacts are left untouched (historical spike snapshot).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import anthropic

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from showtype.rubric import load_rubric  # noqa: E402
from showtype.scorer import MODEL, score_show  # noqa: E402

PHASE0_CSV = REPO / "docs" / "phase0-scores.csv"
OUT_CSV = REPO / "docs" / "baseline-scores.csv"


def gold_set_titles() -> list[str]:
    seen: list[str] = []
    with open(PHASE0_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["show"] not in seen:
                seen.append(row["show"])
    return seen


def _norm(name: str) -> str:
    return name.split("(")[0].strip().lower()


def main() -> int:
    rubric_text, axes = load_rubric(REPO / "docs" / "rubric.md")
    axis_names = [a.name for a in axes]
    titles = gold_set_titles()
    client = anthropic.Anthropic()  # one client -> reuses the cached rubric prefix

    rows: list[dict[str, object]] = []
    for i, title in enumerate(titles, 1):
        print(f"[{i:>2}/{len(titles)}] scoring {title} ...", file=sys.stderr, flush=True)
        result = score_show(title, rubric_text, axis_names, client=client, model=MODEL)
        by_norm = {_norm(s.axis): s for s in result.scores}
        for a in axes:
            s = by_norm.get(_norm(a.name))
            if s is None:
                print(f"     ! {title}: missing axis {a.name}", file=sys.stderr)
                continue
            rows.append(
                {
                    "show": title,
                    "axis": a.name,
                    "value": s.value,
                    "confidence": s.confidence,
                    "justification": s.justification,
                    "model": MODEL,
                }
            )

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["show", "axis", "value", "confidence", "justification", "model"]
        )
        w.writeheader()
        w.writerows(rows)

    print(
        f"\nwrote {len(rows)} scores for {len(titles)} shows -> {OUT_CSV.relative_to(REPO)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
