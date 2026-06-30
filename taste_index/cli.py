"""Command-line entry point for the Taste Index.

    python -m taste_index init-db          # create the DB and seed the 8 axes
    python -m taste_index axes              # list the seeded axes
    python -m taste_index backfill          # load docs/baseline-scores.csv into the DB
    python -m taste_index score "The Wire"  # score one show via the Claude API
    python -m taste_index score-all --file shows.txt --skip-existing  # batch-score many
    python -m taste_index show "The Wire"   # print stored scores for a show
"""
from __future__ import annotations

import argparse
import csv
import sys

from . import db
from .rubric import load_rubric

DEFAULT_RUBRIC = "docs/rubric.md"
DEFAULT_BASELINE_CSV = "docs/baseline-scores.csv"  # model-scored under current rubric
PHASE0_MODEL = "phase0-handscored"  # fallback when a CSV has no `model` column


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
            model = (r.get("model") or "").strip() or PHASE0_MODEL
            by_show.setdefault(r["show"], []).append(
                (axis_id, int(r["value"]), r["confidence"], r["justification"], model)
            )

    if skipped:
        print(f"  ! unknown axes skipped: {', '.join(sorted(skipped))}", file=sys.stderr)

    total = 0
    for title, rows in by_show.items():
        show_id = db.upsert_show(conn, title)
        db.save_scores(conn, show_id, rows)
        total += len(rows)
    print(f"Backfilled {len(by_show)} shows / {total} scores from {args.csv}.")
    return 0


def _collect_titles(positional: list[str], file: str | None) -> list[str]:
    titles = list(positional)
    if file:
        with open(file, encoding="utf-8") as f:
            titles += [
                ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")
            ]
    seen: set[str] = set()
    return [t for t in titles if not (t in seen or seen.add(t))]


def cmd_score_all(args: argparse.Namespace) -> int:
    """Score many shows via the Claude API and save them to the DB."""
    import anthropic

    from .scorer import score_show

    rubric_text, _ = load_rubric(args.rubric)
    conn = db.connect(args.db)
    axis_rows = db.get_axes(conn)
    if not axis_rows:
        print("No axes seeded. Run 'init-db' first.", file=sys.stderr)
        return 1
    axis_names = [r["name"] for r in axis_rows]
    axis_id_by_norm = {_normalize(r["name"]): int(r["id"]) for r in axis_rows}

    titles = _collect_titles(args.titles, args.file)
    if not titles:
        print("No titles given. Pass titles as arguments or via --file.", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()  # shared client -> reuses the cached rubric prefix
    existing = {r["title"] for r in conn.execute("SELECT title FROM show")}
    n = len(titles)
    saved_shows = saved_scores = 0
    skipped: list[str] = []
    failed: list[str] = []

    for i, title in enumerate(titles, 1):
        if args.skip_existing and title in existing:
            print(f"[{i}/{n}] skip (already in DB): {title}", file=sys.stderr)
            skipped.append(title)
            continue
        print(f"[{i}/{n}] scoring {title} ...", file=sys.stderr, flush=True)
        try:
            result = score_show(title, rubric_text, axis_names, client=client, model=args.model)
        except Exception as e:  # one bad show shouldn't abort the batch
            print(f"  ! failed: {e}", file=sys.stderr)
            failed.append(title)
            continue
        rows: list[tuple[int, int, str, str, str]] = []
        for s in result.scores:
            axis_id = axis_id_by_norm.get(_normalize(s.axis))
            if axis_id is not None:
                rows.append((axis_id, s.value, s.confidence, s.justification, args.model))
        show_id = db.upsert_show(conn, title)
        db.save_scores(conn, show_id, rows)
        saved_shows += 1
        saved_scores += len(rows)

    print(f"\nSaved {saved_shows} shows / {saved_scores} scores to {args.db}.")
    if skipped:
        print(f"Skipped {len(skipped)} already in DB.")
    if failed:
        print(f"Failed: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Re-score shows live and diff against their stored (Phase 0) baseline.

    Live scores are computed in memory and NOT saved, so the baseline is preserved.
    """
    from .scorer import score_show  # lazy import (needs anthropic + API key)

    rubric_text, _ = load_rubric(args.rubric)
    conn = db.connect(args.db)
    axis_rows = db.get_axes(conn)
    if not axis_rows:
        print("No axes seeded. Run 'init-db' first.", file=sys.stderr)
        return 1
    axis_order = [r["name"] for r in axis_rows]

    all_deltas: list[int] = []
    for title in args.titles:
        baseline_rows = db.get_show_scores(conn, title)
        if not baseline_rows:
            print(f"\n{title}: no baseline stored — skipped (run 'backfill').", file=sys.stderr)
            continue
        base = {_normalize(r["axis"]): r for r in baseline_rows}

        print(f"\nScoring {title!r} live with {args.model} ...", file=sys.stderr)
        live = score_show(title, rubric_text, axis_order, model=args.model)
        live_by = {_normalize(s.axis): s for s in live.scores}

        print(f"\n{title}")
        print(f"{'Axis':<22} {'P0':>3} {'Live':>4} {'Δ':>3}  {'P0-conf':<8} Live-conf")
        print("-" * 58)
        for name in axis_order:
            k = _normalize(name)
            b, l = base.get(k), live_by.get(k)
            if b is None or l is None:
                continue
            delta = l.value - b["value"]
            all_deltas.append(abs(delta))
            print(
                f"{name:<22} {b['value']:>3} {l.value:>4} {delta:>+3}  "
                f"{b['confidence']:<8} {l.confidence}"
            )

    if all_deltas:
        n = len(all_deltas)
        exact = sum(d == 0 for d in all_deltas)
        within1 = sum(d <= 1 for d in all_deltas)
        print(
            f"\nSummary over {n} axis comparisons: "
            f"mean |Δ| = {sum(all_deltas)/n:.2f}, max |Δ| = {max(all_deltas)}, "
            f"exact = {exact} ({100*exact//n}%), within 1 = {within1} ({100*within1//n}%)"
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

    sp = sub.add_parser("score-all", help="score many shows via the Claude API and save")
    sp.add_argument("titles", nargs="*", help="show titles")
    sp.add_argument("--file", help="file with one show title per line (# comments allowed)")
    sp.add_argument("--rubric", default=DEFAULT_RUBRIC)
    sp.add_argument("--model", default="claude-opus-4-8")
    sp.add_argument(
        "--skip-existing", action="store_true", help="skip shows already in the DB"
    )
    sp.set_defaults(func=cmd_score_all)

    sp = sub.add_parser("backfill", help="load baseline scores from a CSV into the DB")
    sp.add_argument("--csv", default=DEFAULT_BASELINE_CSV)
    sp.set_defaults(func=cmd_backfill)

    sp = sub.add_parser("diff", help="re-score live and diff against the stored baseline")
    sp.add_argument("titles", nargs="+")
    sp.add_argument("--rubric", default=DEFAULT_RUBRIC)
    sp.add_argument("--model", default="claude-opus-4-8")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("show", help="print stored scores for a show")
    sp.add_argument("title")
    sp.set_defaults(func=cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
