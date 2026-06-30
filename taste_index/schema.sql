-- The Taste Index — Phase 1 data model (SQLite)
--
-- `axis` is seeded verbatim from docs/rubric.md (the eight axis definitions).
-- `show` and `score` hold scored shows: one score row per (show, axis).

PRAGMA foreign_keys = ON;

-- The eight scoring axes, seeded from docs/rubric.md. `id` is the canonical
-- 1..8 position; `definition` is the verbatim axis section from the rubric.
CREATE TABLE IF NOT EXISTS axis (
    id         INTEGER PRIMARY KEY,        -- 1..8 (position in the rubric)
    slug       TEXT NOT NULL UNIQUE,       -- e.g. "institutional-sweep"
    name       TEXT NOT NULL,              -- canonical short name, e.g. "Institutional Sweep"
    definition TEXT NOT NULL               -- verbatim section text from docs/rubric.md
);

-- A scored show.
CREATE TABLE IF NOT EXISTS show (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL UNIQUE,
    genre      TEXT,                          -- primary genre tag (see docs/genres.csv)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One axis score for one show. (show_id, axis_id) is unique: re-scoring a show
-- replaces its prior scores in place.
CREATE TABLE IF NOT EXISTS score (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id       INTEGER NOT NULL REFERENCES show(id) ON DELETE CASCADE,
    axis_id       INTEGER NOT NULL REFERENCES axis(id),
    value         INTEGER NOT NULL CHECK (value BETWEEN 0 AND 10),
    confidence    TEXT    NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    justification TEXT    NOT NULL,
    model         TEXT    NOT NULL,        -- model id that produced the score
    scored_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (show_id, axis_id)
);
