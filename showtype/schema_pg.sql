-- Show Type — data model (PostgreSQL).
--
-- Mirror of schema.sql (the SQLite schema) with identical table names, column
-- names, uniqueness constraints, checks, and foreign keys. Differences are only
-- the Postgres spellings: GENERATED ALWAYS AS IDENTITY for autoincrement PKs and
-- TIMESTAMP DEFAULT now() for created_at / scored_at.

-- The eight scoring axes, seeded from docs/rubric.md. `id` is the canonical
-- 1..8 position (seeded explicitly, so no identity).
CREATE TABLE IF NOT EXISTS axis (
    id         INTEGER PRIMARY KEY,        -- 1..8 (position in the rubric)
    slug       TEXT NOT NULL UNIQUE,       -- e.g. "institutional-sweep"
    name       TEXT NOT NULL,              -- canonical short name, e.g. "Institutional Sweep"
    definition TEXT NOT NULL               -- verbatim section text from docs/rubric.md
);

-- A scored show.
CREATE TABLE IF NOT EXISTS show (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title           TEXT NOT NULL UNIQUE,
    genre           TEXT,                     -- primary genre (rank 0), denormalized for display
    quality         INTEGER,                  -- model-judged execution score 0-10 (evaluative; see docs/quality.csv)
    quality_reason  TEXT,                     -- one-to-two sentence justification for quality
    summary         TEXT,                     -- short spoiler-free premise
    episodes        INTEGER,                  -- approximate total episode count (model estimate; may be null)
    seasons         INTEGER,                  -- number of seasons (model estimate; may be null)
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- A show may carry several genres; rank 0 is the primary. See docs/genres.csv.
CREATE TABLE IF NOT EXISTS show_genre (
    show_id INTEGER NOT NULL REFERENCES show(id) ON DELETE CASCADE,
    genre   TEXT    NOT NULL,
    rank    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (show_id, genre)
);

-- One axis score for one show. (show_id, axis_id) is unique: re-scoring a show
-- replaces its prior scores in place.
CREATE TABLE IF NOT EXISTS score (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    show_id       INTEGER NOT NULL REFERENCES show(id) ON DELETE CASCADE,
    axis_id       INTEGER NOT NULL REFERENCES axis(id),
    value         INTEGER NOT NULL CHECK (value BETWEEN 0 AND 10),
    confidence    TEXT    NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    justification TEXT    NOT NULL,
    model         TEXT    NOT NULL,        -- model id that produced the score
    scored_at     TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (show_id, axis_id)
);
