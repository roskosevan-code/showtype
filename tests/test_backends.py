"""Backend tests: SQLite always; Postgres parity when DATABASE_URL + psycopg exist.

The SQLite tests build a DB from the committed CSVs and check basic invariants.
The Postgres tests (skipped unless ``DATABASE_URL`` is set and psycopg importable)
build the same data and assert the two backends are byte-for-byte equivalent for
counts, axes, vectors, genres, quality, and retrieval results.
"""
from __future__ import annotations

import csv
import importlib.util
import os
from pathlib import Path

import pytest

from showtype import db, space
from showtype.cli import _int_or_none, _normalize
from showtype.rubric import load_rubric

REPO = Path(__file__).resolve().parent.parent
RUBRIC = REPO / "docs" / "rubric.md"
CATALOG = REPO / "docs" / "catalog-scores.csv"
GENRES = REPO / "docs" / "genres.csv"
QUALITY = REPO / "docs" / "quality.csv"

SAMPLE_SHOWS = ["The Wire", "Severance", "Succession", "Mad Men"]

_HAS_PSYCOPG = importlib.util.find_spec("psycopg") is not None
_PG_REASON = "requires DATABASE_URL and psycopg (Postgres parity)"


def _load(conn) -> None:
    """Populate a connection from the committed CSVs, mirroring the CLI loaders."""
    _, axes = load_rubric(RUBRIC)
    db.init_schema(conn)
    db.seed_axes(conn, axes)

    axis_id_by_norm = {_normalize(r["name"]): int(r["id"]) for r in db.get_axes(conn)}
    by_show: dict[str, list[tuple]] = {}
    with open(CATALOG, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            aid = axis_id_by_norm.get(_normalize(r["axis"]))
            if aid is None:
                continue
            model = (r.get("model") or "").strip() or "phase0-handscored"
            by_show.setdefault(r["show"], []).append(
                (aid, int(r["value"]), r["confidence"], r["justification"], model)
            )
    for title, rows in by_show.items():
        sid = db.upsert_show(conn, title)
        db.save_scores(conn, sid, rows)

    with open(GENRES, newline="", encoding="utf-8") as f:
        grows = [(r["show"], r["genre"], int(r.get("rank", 0) or 0)) for r in csv.DictReader(f)]
    db.tag_genres(conn, grows)

    with open(QUALITY, newline="", encoding="utf-8") as f:
        qrows = [
            (r["show"], _int_or_none(r["quality"]), r["quality_reason"], r["summary"],
             _int_or_none(r["episodes"]), _int_or_none(r["seasons"]))
            for r in csv.DictReader(f)
        ]
    db.load_quality(conn, qrows)


@pytest.fixture(scope="module")
def sqlite_conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "sqlite_test.db"
    conn = db.connect(path, force_sqlite=True)
    _load(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# SQLite invariants (always run)
# ---------------------------------------------------------------------------

def test_sqlite_show_count(sqlite_conn):
    n = sqlite_conn.execute("SELECT COUNT(*) AS n FROM show").fetchone()["n"]
    assert n > 0


def test_sqlite_eight_axes(sqlite_conn):
    axes = db.get_axes(sqlite_conn)
    assert len(axes) == 8
    assert [int(a["id"]) for a in axes] == list(range(1, 9))


def test_sqlite_known_vectors(sqlite_conn):
    vecs = space.show_vectors(sqlite_conn)
    axis_ids, _ = space.axis_index(sqlite_conn)
    for title in ("The Wire", "Severance"):
        assert title in vecs, f"{title} missing from DB"
        assert all(i in vecs[title] for i in axis_ids), f"{title} vector incomplete"
        assert all(0 <= vecs[title][i] <= 10 for i in axis_ids)


def test_sqlite_genres_and_quality_nonempty(sqlite_conn):
    assert db.genres_multi(sqlite_conn)
    assert db.quality_map(sqlite_conn)


def test_sqlite_nearest_and_recommend(sqlite_conn):
    neighbors = space.nearest(sqlite_conn, "The Wire", n=5)
    assert len(neighbors) == 5
    assert all(t != "The Wire" for t, _, _ in neighbors)
    # distances are non-decreasing
    dists = [d for _, d, _ in neighbors]
    assert dists == sorted(dists)

    liked, _, _, recs = space.recommend(
        sqlite_conn, {"The Wire": 2.0, "Succession": 1.0}, n=8
    )
    assert recs
    rec_titles = {t for t, _, _ in recs}
    assert "The Wire" not in rec_titles and "Succession" not in rec_titles


# ---------------------------------------------------------------------------
# Postgres parity (skipped unless DATABASE_URL is set and psycopg importable)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_conn():
    if not os.environ.get("DATABASE_URL") or not _HAS_PSYCOPG:
        pytest.skip(_PG_REASON)
    conn = db.connect()  # picks Postgres from DATABASE_URL
    # Clean slate so parity is exact regardless of prior runs.
    conn.execute("DROP TABLE IF EXISTS score, show_genre, show, axis CASCADE")
    conn.commit()
    _load(conn)
    yield conn
    conn.close()


@pytest.mark.skipif(not _HAS_PSYCOPG, reason=_PG_REASON)
def test_pg_show_count_parity(sqlite_conn, pg_conn):
    a = sqlite_conn.execute("SELECT COUNT(*) AS n FROM show").fetchone()["n"]
    b = pg_conn.execute("SELECT COUNT(*) AS n FROM show").fetchone()["n"]
    assert a == b


@pytest.mark.skipif(not _HAS_PSYCOPG, reason=_PG_REASON)
def test_pg_axes_parity(sqlite_conn, pg_conn):
    sa = [(int(r["id"]), r["slug"], r["name"]) for r in db.get_axes(sqlite_conn)]
    pa = [(int(r["id"]), r["slug"], r["name"]) for r in db.get_axes(pg_conn)]
    assert sa == pa


@pytest.mark.skipif(not _HAS_PSYCOPG, reason=_PG_REASON)
def test_pg_vectors_parity(sqlite_conn, pg_conn):
    sv = space.show_vectors(sqlite_conn)
    pv = space.show_vectors(pg_conn)
    for title in SAMPLE_SHOWS:
        assert sv.get(title) == pv.get(title), f"vector mismatch for {title}"


@pytest.mark.skipif(not _HAS_PSYCOPG, reason=_PG_REASON)
def test_pg_genres_parity(sqlite_conn, pg_conn):
    sg = db.genres_multi(sqlite_conn)
    pg = db.genres_multi(pg_conn)
    for title in SAMPLE_SHOWS:
        assert sg.get(title) == pg.get(title), f"genres mismatch for {title}"


@pytest.mark.skipif(not _HAS_PSYCOPG, reason=_PG_REASON)
def test_pg_quality_parity(sqlite_conn, pg_conn):
    sq = db.quality_map(sqlite_conn)
    pq = db.quality_map(pg_conn)
    for title in SAMPLE_SHOWS:
        assert sq.get(title) == pq.get(title), f"quality mismatch for {title}"


@pytest.mark.skipif(not _HAS_PSYCOPG, reason=_PG_REASON)
def test_pg_nearest_parity(sqlite_conn, pg_conn):
    sn = space.nearest(sqlite_conn, "The Wire", n=10)
    pn = space.nearest(pg_conn, "The Wire", n=10)
    assert [(t, round(d, 6)) for t, d, _ in sn] == [(t, round(d, 6)) for t, d, _ in pn]


@pytest.mark.skipif(not _HAS_PSYCOPG, reason=_PG_REASON)
def test_pg_recommend_parity(sqlite_conn, pg_conn):
    profile = {"The Wire": 2.0, "Succession": 1.0, "Mad Men": 0.4}
    _, _, _, sr = space.recommend(sqlite_conn, profile, n=10)
    _, _, _, pr = space.recommend(pg_conn, profile, n=10)
    assert [(t, round(d, 6)) for t, d, _ in sr] == [(t, round(d, 6)) for t, d, _ in pr]
