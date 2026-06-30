"""SQLite access layer for the Taste Index."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .rubric import Axis

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB_PATH = "taste_index.db"


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_SHOW_COLUMNS = {
    "genre": "TEXT",
    "quality": "INTEGER",
    "quality_reason": "TEXT",
    "summary": "TEXT",
    "episodes": "INTEGER",
    "seasons": "INTEGER",
}


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    # Idempotent migration: add any new show columns to pre-existing DBs.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(show)")}
    with conn:
        for name, typ in _SHOW_COLUMNS.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE show ADD COLUMN {name} {typ}")


def seed_axes(conn: sqlite3.Connection, axes: list[Axis]) -> None:
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


def get_axes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM axis ORDER BY id").fetchall()


def upsert_show(conn: sqlite3.Connection, title: str) -> int:
    with conn:
        conn.execute(
            "INSERT INTO show (title) VALUES (?) ON CONFLICT(title) DO NOTHING",
            (title,),
        )
    row = conn.execute("SELECT id FROM show WHERE title = ?", (title,)).fetchone()
    return int(row["id"])


def save_scores(
    conn: sqlite3.Connection,
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
            "  scored_at = datetime('now')",
            [(show_id, *r) for r in rows],
        )


def tag_genres(conn: sqlite3.Connection, rows: list[tuple[str, str, int]]) -> int:
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


def genre_map(conn: sqlite3.Connection) -> dict[str, str]:
    """title -> primary genre."""
    return {
        r["title"]: r["genre"]
        for r in conn.execute("SELECT title, genre FROM show WHERE genre IS NOT NULL")
    }


def genres_multi(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """title -> all genres, primary first."""
    out: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT sh.title AS title, sg.genre AS genre FROM show_genre sg "
        "JOIN show sh ON sh.id = sg.show_id ORDER BY sg.rank"
    ):
        out.setdefault(r["title"], []).append(r["genre"])
    return out


def shows_with_genre(conn: sqlite3.Connection, genre: str) -> set[str]:
    return {
        r["title"]
        for r in conn.execute(
            "SELECT sh.title AS title FROM show_genre sg "
            "JOIN show sh ON sh.id = sg.show_id WHERE sg.genre = ?",
            (genre,),
        )
    }


def get_genres(conn: sqlite3.Connection) -> list[str]:
    """All genres that appear as any tag, ordered by frequency."""
    return [
        r["genre"]
        for r in conn.execute(
            "SELECT genre, COUNT(*) n FROM show_genre GROUP BY genre ORDER BY n DESC, genre"
        )
    ]


def load_quality(conn: sqlite3.Connection, rows: list[tuple]) -> int:
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


def get_show_meta(conn: sqlite3.Connection, title: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT genre, quality, quality_reason, summary, episodes, seasons "
        "FROM show WHERE title=?",
        (title,),
    ).fetchone()


def quality_map(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        r["title"]: r["quality"]
        for r in conn.execute("SELECT title, quality FROM show WHERE quality IS NOT NULL")
    }


def get_show_scores(conn: sqlite3.Connection, title: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.name AS axis, s.value, s.confidence, s.justification, s.model "
        "FROM score s "
        "JOIN axis a ON a.id = s.axis_id "
        "JOIN show sh ON sh.id = s.show_id "
        "WHERE sh.title = ? "
        "ORDER BY a.id",
        (title,),
    ).fetchall()
