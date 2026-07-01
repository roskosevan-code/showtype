"""Database access layer for the Taste Index.

Dual-backend: SQLite by default (stdlib, zero-dependency), or PostgreSQL when
``DATABASE_URL`` is set (via psycopg v3, imported lazily on that path only).

Both backends expose the identical schema (``axis`` / ``show`` / ``show_genre`` /
``score``) and the same connection surface used across the codebase:
``.execute(sql, params=())``, ``.executemany(sql, seq)``, ``.executescript(sql)``,
``with conn:`` transaction semantics, and cursor results supporting ``.fetchone()``,
``.fetchall()``, ``.rowcount`` plus by-name (``row["title"]``) and ``dict(row)`` access.

SQLite behaviour is preserved exactly: ``connect`` returns a real ``sqlite3.Connection``
(``row_factory=sqlite3.Row``, ``PRAGMA foreign_keys=ON``). Only the Postgres path is
wrapped. SQL is written with ``?`` placeholders throughout; the Postgres wrapper
translates them to ``%s`` transparently.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .rubric import Axis

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_SCHEMA_PG_PATH = Path(__file__).with_name("schema_pg.sql")
DEFAULT_DB_PATH = "taste_index.db"


def _translate(sql: str) -> str:
    """Rewrite ``?`` placeholders to psycopg's ``%s``, skipping string literals.

    Also doubles any literal ``%`` (psycopg's placeholder char) outside strings.
    The codebase's SQL uses ``?`` only as placeholders and contains no literal
    ``%``, so this is a faithful, minimal translation.
    """
    out: list[str] = []
    in_str = False
    for c in sql:
        if c == "'":
            in_str = not in_str
            out.append(c)
        elif not in_str and c == "%":
            out.append("%%")
        elif not in_str and c == "?":
            out.append("%s")
        else:
            out.append(c)
    return "".join(out)


class PgConnection:
    """Thin wrapper over a psycopg3 connection matching the sqlite3 surface used here.

    Rows come back as ``dict_row`` mappings, so ``row["col"]`` and ``dict(row)`` both
    work. ``with conn:`` commits on success / rolls back on error (and, unlike raw
    psycopg, does NOT close the connection — matching sqlite3 semantics).
    """

    backend = "postgres"

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params=()):  # noqa: ANN001
        return self._conn.execute(_translate(sql), tuple(params))

    def executemany(self, sql: str, seq):  # noqa: ANN001
        cur = self._conn.cursor()
        cur.executemany(_translate(sql), [tuple(p) for p in seq])
        return cur

    def executescript(self, sql: str):  # noqa: ANN001
        # No params in a schema script; run the multi-statement string as-is.
        self._conn.execute(sql)
        self._conn.commit()

    def cursor(self):
        return self._conn.cursor()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PgConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        return False


def _resolve_backend(backend: str | None, force_sqlite: bool) -> str:
    if force_sqlite or backend == "sqlite":
        return "sqlite"
    if backend == "postgres":
        return "postgres"
    return "postgres" if os.environ.get("DATABASE_URL") else "sqlite"


def connect(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    backend: str | None = None,
    force_sqlite: bool = False,
):
    """Open a DB connection.

    - Default: SQLite at ``db_path`` (as today), unless ``DATABASE_URL`` is set, in
      which case Postgres is used via psycopg v3 (imported lazily).
    - ``force_sqlite=True`` (or ``backend="sqlite"``) forces SQLite regardless of env
      — used by ``scripts/build_static.py`` so the offline build stays zero-dependency.
    """
    if _resolve_backend(backend, force_sqlite) == "sqlite":
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    import psycopg  # lazy: only imported on the Postgres path
    from psycopg.rows import dict_row

    dsn = os.environ["DATABASE_URL"]
    return PgConnection(psycopg.connect(dsn, row_factory=dict_row))


def _is_sqlite(conn) -> bool:  # noqa: ANN001
    return isinstance(conn, sqlite3.Connection)


_SHOW_COLUMNS = {
    "genre": "TEXT",
    "quality": "INTEGER",
    "quality_reason": "TEXT",
    "summary": "TEXT",
    "episodes": "INTEGER",
    "seasons": "INTEGER",
}


def init_schema(conn) -> None:  # noqa: ANN001
    if _is_sqlite(conn):
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        # Idempotent migration: add any new show columns to pre-existing DBs.
        existing = {r[1] for r in conn.execute("PRAGMA table_info(show)")}
    else:
        conn.executescript(_SCHEMA_PG_PATH.read_text(encoding="utf-8"))
        existing = {
            r["column_name"]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'show'"
            )
        }
    with conn:
        for name, typ in _SHOW_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE show ADD COLUMN {name} {typ}")


def seed_axes(conn, axes: list[Axis]) -> None:  # noqa: ANN001
    """Insert/replace the eight axes verbatim from the rubric."""
    with conn:
        conn.executemany(
            "INSERT INTO axis (id, slug, name, definition) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  slug = excluded.slug, "
            "  name = excluded.name, "
            "  definition = excluded.definition",
            [(a.position, a.slug, a.name, a.definition) for a in axes],
        )


def get_axes(conn):  # noqa: ANN001
    return conn.execute("SELECT * FROM axis ORDER BY id").fetchall()


def upsert_show(conn, title: str) -> int:  # noqa: ANN001
    with conn:
        conn.execute(
            "INSERT INTO show (title) VALUES (?) ON CONFLICT(title) DO NOTHING",
            (title,),
        )
    row = conn.execute("SELECT id FROM show WHERE title = ?", (title,)).fetchone()
    return int(row["id"])


def save_scores(
    conn,  # noqa: ANN001
    show_id: int,
    rows: list[tuple[int, int, str, str, str]],
) -> None:
    """Upsert scores. Each row is (axis_id, value, confidence, justification, model)."""
    with conn:
        conn.executemany(
            "INSERT INTO score (show_id, axis_id, value, confidence, justification, model) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(show_id, axis_id) DO UPDATE SET "
            "  value = excluded.value, "
            "  confidence = excluded.confidence, "
            "  justification = excluded.justification, "
            "  model = excluded.model, "
            "  scored_at = CURRENT_TIMESTAMP",
            [(show_id, *r) for r in rows],
        )


def tag_genres(conn, rows: list[tuple[str, str, int]]) -> int:  # noqa: ANN001
    """Load (title, genre, rank) genre memberships.

    Replaces all genres for the tagged shows; rank 0 is mirrored into show.genre
    as the primary. Returns the number of membership rows inserted.
    """
    ids = {r["title"]: int(r["id"]) for r in conn.execute("SELECT id, title FROM show")}
    present = [(t, g, rank) for t, g, rank in rows if t in ids]
    tagged_ids = {ids[t] for t, _, _ in present}
    inserted = 0
    with conn:
        for sid in tagged_ids:
            conn.execute("DELETE FROM show_genre WHERE show_id = ?", (sid,))
            conn.execute("UPDATE show SET genre = NULL WHERE id = ?", (sid,))
        for title, genre, rank in present:
            conn.execute(
                "INSERT INTO show_genre (show_id, genre, rank) VALUES (?, ?, ?)",
                (ids[title], genre, rank),
            )
            inserted += 1
            if rank == 0:
                conn.execute(
                    "UPDATE show SET genre = ? WHERE id = ?", (genre, ids[title])
                )
    return inserted


def genre_map(conn) -> dict[str, str]:  # noqa: ANN001
    """title -> primary genre."""
    return {
        r["title"]: r["genre"]
        for r in conn.execute("SELECT title, genre FROM show WHERE genre IS NOT NULL")
    }


def genres_multi(conn) -> dict[str, list[str]]:  # noqa: ANN001
    """title -> all genres, primary first."""
    out: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT sh.title AS title, sg.genre AS genre FROM show_genre sg "
        "JOIN show sh ON sh.id = sg.show_id ORDER BY sg.rank"
    ):
        out.setdefault(r["title"], []).append(r["genre"])
    return out


def shows_with_genre(conn, genre: str) -> set[str]:  # noqa: ANN001
    return {
        r["title"]
        for r in conn.execute(
            "SELECT sh.title AS title FROM show_genre sg "
            "JOIN show sh ON sh.id = sg.show_id WHERE sg.genre = ?",
            (genre,),
        )
    }


def get_genres(conn) -> list[str]:  # noqa: ANN001
    """All genres that appear as any tag, ordered by frequency."""
    return [
        r["genre"]
        for r in conn.execute(
            "SELECT genre, COUNT(*) n FROM show_genre GROUP BY genre ORDER BY n DESC, genre"
        )
    ]


def load_quality(conn, rows: list[tuple]) -> int:  # noqa: ANN001
    """Apply quality/summary/episode metadata. Rows: (title, quality, reason,
    summary, episodes, seasons). Updates only existing shows; returns count updated."""
    updated = 0
    with conn:
        for title, quality, reason, summary, episodes, seasons in rows:
            cur = conn.execute(
                "UPDATE show SET quality=?, quality_reason=?, summary=?, episodes=?, "
                "seasons=? WHERE title=?",
                (quality, reason, summary, episodes, seasons, title),
            )
            updated += cur.rowcount
    return updated


def get_show_meta(conn, title: str):  # noqa: ANN001
    return conn.execute(
        "SELECT genre, quality, quality_reason, summary, episodes, seasons "
        "FROM show WHERE title=?",
        (title,),
    ).fetchone()


def quality_map(conn) -> dict[str, int]:  # noqa: ANN001
    return {
        r["title"]: r["quality"]
        for r in conn.execute("SELECT title, quality FROM show WHERE quality IS NOT NULL")
    }


def get_show_scores(conn, title: str):  # noqa: ANN001
    return conn.execute(
        "SELECT a.name AS axis, s.value, s.confidence, s.justification, s.model "
        "FROM score s "
        "JOIN axis a ON a.id = s.axis_id "
        "JOIN show sh ON sh.id = s.show_id "
        "WHERE sh.title = ? "
        "ORDER BY a.id",
        (title,),
    ).fetchall()
