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


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))


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
