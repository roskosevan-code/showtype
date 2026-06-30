"""Command-line entry point for the Taste Index.

    python -m taste_index init-db          # create the DB and seed the 8 axes
    python -m taste_index axes              # list the seeded axes
    python -m taste_index backfill          # load docs/phase0-scores.csv into the DB
    python -m taste_index score "The Wire"  # score a show via the Claude API
    python -m taste_index show "The Wire"   # print stored scores for a show
"""
from __future__ import annotations

import argparse
import csv
import sys

from . import db
from .rubric import load_rubric

DEFAULT_RUBRIC = "docs/rubric.md"
DEFAULT_PHASE0_CSV = "docs/phase0-scores.csv"
PHASE0_MODEL = "phase0-handscored"


def _normalize(name: str) -> str:
    return name.split("(")[0].strip().lower()


def cmd_init_db(args: argparse.Namespace) -> int:
    _, axes = load_rubric(args.rubric)
    conn = db.connect(args.db)
    db.init_schema(conn)
    db.seed_axes(conn, axes)
    print(f"Initialized {args.db} and seeded {len(axes)} axes from {args.rubric}:")
    for a in axes:
        print(f"  {a.position}. {a.name}")
    return 0


def cmd_axes(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    rows = db.get_axes(conn)
    if not rows:
        print("No axes seeded. Run 'init-db' first.", file=sys.stderr)
        return 1
    for r in rows:
        print(f"{r['id']}. {r['name']} ({r['slug']})")
    return 0


def _print_scores(title: str, rows) -> None:
    print(f"\n{title}")
    print(f"{'Axis':<22} {'Val':>3}  {'Conf':<6} Justification")
    print("-" * 80)
    for r in rows:
        print(
            f"{r['axis']:<22} {r['value']:>3}  {r['confidence']:<6} {r['justification']}"
        )


def cmd_score(args: argparse.Namespace) -> int:
    from .scorer import score_show  # imported lazily so other cmds don't need anthropic

    rubric_text, _ = load_rubric(args.rubric)
    conn = db.connect(args.db)
    axis_rows = db.get_axes(conn)
    if not axis_rows:
        print("No axes seeded. Run 'init-db' first.", file=sys.stderr)
        return 1
    axis_names = [r["name"] for r in axis_rows]
    axis_id_by_norm = {_normalize(r["name"]): int(r["id"]) for r in axis_rows}

    print(f"Scoring {args.title!r} with {args.model} ...", file=sys.stderr)
    result = score_show(args.title, rubric_text, axis_names, model=args.model)

    rows: list[tuple[int, int, str, str, str]] = []
    seen: set[int] = set()
    for s in result.scores:
        axis_id = axis_id_by_norm.get(_normalize(s.axis))
        if axis_id is None:
            print(f"  ! unknown axis from model: {s.axis!r} — skipped", file=sys.stderr)
            continue
        seen.add(axis_id)
        rows.append((axis_id, s.value, s.confidence, s.justification, args.model))

    missing = [r["name"] for r in axis_rows if int(r["id"]) not in seen]
    if missing:
        print(f"  ! model omitted axes: {', '.join(missing)}", file=sys.stderr)

    show_id = db.upsert_show(conn, args.title)
    db.save_scores(conn, show_id, rows)
    _print_scores(args.title, db.get_show_scores(conn, args.title))
    print(f"\nSaved {len(rows)} scores to {args.db}.")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    axis_rows = db.get_axes(conn)
    if not axis_rows:
        print("No axes seeded. Run 'init-db' first.", file=sys.stderr)
        return 1
    axis_id_by_norm = {_normalize(r["name"]): int(r["id"]) for r in axis_rows}

    # Group CSV rows by show.
    by_show: dict[str, list[tuple[int, int, str, str, str]]] = {}
    skipped: set[str] = set()
    with open(args.csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            axis_id = axis_id_by_norm.get(_normalize(r["axis"]))
            if axis_id is None:
                skipped.add(r["axis"])
                continue
            by_show.setdefault(r["show"], []).append(
                (axis_id, int(r["value"]), r["confidence"], r["justification"], PHASE0_MODEL)
            )

    if skipped:
        print(f"  ! unknown axes skipped: {', '.join(sorted(skipped))}", file=sys.stderr)

    total = 0
    for title, rows in by_show.items():
        show_id = db.upsert_show(conn, title)
        db.save_scores(conn, show_id, rows)
        total += len(rows)
    print(
        f"Backfilled {len(by_show)} shows / {total} scores from {args.csv} "
        f"(model={PHASE0_MODEL})."
    )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    rows = db.get_show_scores(conn, args.title)
    if not rows:
        print(f"No scores stored for {args.title!r}.", file=sys.stderr)
        return 1
    _print_scores(args.title, rows)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taste_index", description=__doc__)
    p.add_argument("--db", default=db.DEFAULT_DB_PATH, help="SQLite DB path")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init-db", help="create the DB and seed the 8 axes")
    sp.add_argument("--rubric", default=DEFAULT_RUBRIC)
    sp.set_defaults(func=cmd_init_db)

    sp = sub.add_parser("axes", help="list the seeded axes")
    sp.set_defaults(func=cmd_axes)

    sp = sub.add_parser("score", help="score a show via the Claude API")
    sp.add_argument("title")
    sp.add_argument("--rubric", default=DEFAULT_RUBRIC)
    sp.add_argument("--model", default="claude-opus-4-8")
    sp.set_defaults(func=cmd_score)

    sp = sub.add_parser("backfill", help="load Phase 0 hand-scores from a CSV")
    sp.add_argument("--csv", default=DEFAULT_PHASE0_CSV)
    sp.set_defaults(func=cmd_backfill)

    sp = sub.add_parser("show", help="print stored scores for a show")
    sp.add_argument("title")
    sp.set_defaults(func=cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
