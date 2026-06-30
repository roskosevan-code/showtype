"""Command-line entry point for the Taste Index.

    python -m taste_index init-db          # create the DB and seed the 8 axes
    python -m taste_index axes              # list the seeded axes
    python -m taste_index backfill          # load docs/baseline-scores.csv into the DB
    python -m taste_index score "The Wire"  # score one show via the Claude API
    python -m taste_index score-all --file shows.txt --skip-existing   # sequential
    python -m taste_index score-batch --file shows.txt --skip-existing  # Batches API (50% cost)
    python -m taste_index similar "The Wire"           # nearest shows in taste-space
    python -m taste_index query --where "sweep>=8" --where "register<=4"   # filter by profile
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
DEFAULT_GENRES_CSV = "docs/genres.csv"
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


def cmd_score_batch(args: argparse.Namespace) -> int:
    """Score many shows via the Claude Batches API (50% cost, async) and save them."""
    import time

    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    from .scorer import build_batch_params, parse_message_scores

    rubric_text, _ = load_rubric(args.rubric)
    conn = db.connect(args.db)
    axis_rows = db.get_axes(conn)
    if not axis_rows:
        print("No axes seeded. Run 'init-db' first.", file=sys.stderr)
        return 1
    axis_names = [r["name"] for r in axis_rows]
    axis_id_by_norm = {_normalize(r["name"]): int(r["id"]) for r in axis_rows}

    titles = _collect_titles(args.titles, args.file)
    if args.skip_existing:
        existing = {r["title"] for r in conn.execute("SELECT title FROM show")}
        before = len(titles)
        titles = [t for t in titles if t not in existing]
        print(f"Skipping {before - len(titles)} already in DB.", file=sys.stderr)
    if not titles:
        print("No titles to score.", file=sys.stderr)
        return 1

    # custom_id must be [A-Za-z0-9_-]{1,64}; map synthetic ids back to titles.
    cid_title = {f"sh{i:04d}": t for i, t in enumerate(titles)}
    requests = [
        Request(
            custom_id=cid,
            params=MessageCreateParamsNonStreaming(
                **build_batch_params(title, rubric_text, axis_names, model=args.model)
            ),
        )
        for cid, title in cid_title.items()
    ]

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    print(f"Submitted batch {batch.id} with {len(requests)} requests.", file=sys.stderr)

    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        c = b.request_counts
        print(
            f"  {b.processing_status}: processing={c.processing} succeeded={c.succeeded} "
            f"errored={c.errored}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(args.poll_interval)

    saved_shows = saved_scores = 0
    failed: list[str] = []
    for result in client.messages.batches.results(batch.id):
        title = cid_title.get(result.custom_id, result.custom_id)
        if result.result.type != "succeeded":
            failed.append(f"{title} ({result.result.type})")
            continue
        try:
            parsed = parse_message_scores(result.result.message)
        except Exception as e:
            failed.append(f"{title} (parse: {e})")
            continue
        rows: list[tuple[int, int, str, str, str]] = []
        for s in parsed.scores:
            axis_id = axis_id_by_norm.get(_normalize(s.axis))
            if axis_id is not None:
                rows.append((axis_id, s.value, s.confidence, s.justification, args.model))
        show_id = db.upsert_show(conn, title)
        db.save_scores(conn, show_id, rows)
        saved_shows += 1
        saved_scores += len(rows)

    print(f"\nSaved {saved_shows} shows / {saved_scores} scores to {args.db}.")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed)}", file=sys.stderr)
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


def _vector_header() -> str:
    from .space import AXIS_CODES

    cols = " ".join(f"{c:>4}" for c in AXIS_CODES)
    return cols


def _vector_row(vec: dict[int, int]) -> str:
    return " ".join(f"{vec[i]:>4}" for i in sorted(vec))


def cmd_similar(args: argparse.Namespace) -> int:
    from . import space

    conn = db.connect(args.db)
    try:
        neighbors = space.nearest(conn, args.title, n=args.n)
    except (KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    target = space.show_vectors(conn)[args.title]
    print(f"Nearest {args.n} shows to {args.title!r} in taste-space:\n")
    print(f"{'':<28} {_vector_header()}   dist")
    print(f"{args.title:<28} {_vector_row(target)}      —")
    print("-" * 72)
    for title, dist, vec in neighbors:
        print(f"{title:<28} {_vector_row(vec)}  {dist:>5.2f}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    from . import space

    conn = db.connect(args.db)
    try:
        constraints = [space.parse_constraint(w, conn) for w in args.where]
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if not constraints:
        print("Give at least one --where constraint, e.g. --where 'sweep>=8'.", file=sys.stderr)
        return 1
    matches = space.query(conn, constraints)
    print(f"{len(matches)} shows match {' and '.join(args.where)}:\n")
    print(f"{'':<28} {_vector_header()}")
    print("-" * 66)
    for title, vec in matches:
        print(f"{title:<28} {_vector_row(vec)}")
    return 0


def cmd_tag_genres(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = [
            (r["show"], r["genre"], int(r.get("rank", 0) or 0))
            for r in csv.DictReader(f)
        ]
    inserted = db.tag_genres(conn, rows)
    untagged = conn.execute("SELECT COUNT(*) FROM show WHERE genre IS NULL").fetchone()[0]
    multi = sum(1 for gs in db.genres_multi(conn).values() if len(gs) > 1)
    print(
        f"Loaded {inserted} genre tags from {args.csv} ({multi} multi-genre shows). "
        f"Genres: {db.get_genres(conn)}"
    )
    if untagged:
        print(f"{untagged} shows still have no genre.", file=sys.stderr)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from . import web

    web.serve(db_path=args.db, host=args.host, port=args.port)
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

    sp = sub.add_parser(
        "score-batch", help="score many shows via the Batches API (50% cost, async)"
    )
    sp.add_argument("titles", nargs="*", help="show titles")
    sp.add_argument("--file", help="file with one show title per line (# comments allowed)")
    sp.add_argument("--rubric", default=DEFAULT_RUBRIC)
    sp.add_argument("--model", default="claude-opus-4-8")
    sp.add_argument("--skip-existing", action="store_true", help="skip shows already in the DB")
    sp.add_argument("--poll-interval", type=int, default=30, help="seconds between status polls")
    sp.set_defaults(func=cmd_score_batch)

    sp = sub.add_parser("backfill", help="load baseline scores from a CSV into the DB")
    sp.add_argument("--csv", default=DEFAULT_BASELINE_CSV)
    sp.set_defaults(func=cmd_backfill)

    sp = sub.add_parser("diff", help="re-score live and diff against the stored baseline")
    sp.add_argument("titles", nargs="+")
    sp.add_argument("--rubric", default=DEFAULT_RUBRIC)
    sp.add_argument("--model", default="claude-opus-4-8")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("similar", help="nearest shows in taste-space (no API call)")
    sp.add_argument("title")
    sp.add_argument("-n", type=int, default=5, help="how many neighbors")
    sp.set_defaults(func=cmd_similar)

    sp = sub.add_parser("query", help="find shows matching an axis profile (no API call)")
    sp.add_argument(
        "--where", action="append", default=[],
        help="axis constraint, e.g. 'sweep>=8' or 'register<=4' (repeatable)",
    )
    sp.set_defaults(func=cmd_query)

    sp = sub.add_parser("tag-genres", help="set show genres from a show,genre CSV")
    sp.add_argument("--csv", default=DEFAULT_GENRES_CSV)
    sp.set_defaults(func=cmd_tag_genres)

    sp = sub.add_parser("serve", help="launch the web UI (http.server, no deps)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("show", help="print stored scores for a show")
    sp.add_argument("title")
    sp.set_defaults(func=cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
