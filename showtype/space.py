"""Retrieval over the eight-axis taste-space.

The eight rubric axes form an interpretable 0-10 vector per show, so
similarity is just distance in that space — no embeddings required.
"""
from __future__ import annotations

import math
import sqlite3

# Short column codes for compact vector display, in axis-id order (1..8).
AXIS_CODES = ["Prop", "Scope", "Swp", "Int", "Auth", "Ver", "Den", "Reg"]

# Comparison operators accepted by `query`, longest first so >= parses before >.
_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "=": lambda a, b: a == b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}


def axis_index(conn: sqlite3.Connection) -> tuple[list[int], dict[str, int]]:
    """Return (ordered axis ids, token -> axis_id lookup).

    Tokens resolve by exact slug, then by substring of slug or name
    (so 'sweep' -> institutional-sweep, 'auth' -> authorial-signature).
    """
    rows = conn.execute("SELECT id, slug, name FROM axis ORDER BY id").fetchall()
    axis_ids = [int(r["id"]) for r in rows]
    lookup: dict[str, int] = {}
    for r in rows:
        lookup[r["slug"]] = int(r["id"])
    return axis_ids, lookup


def resolve_axis(token: str, conn: sqlite3.Connection) -> int:
    token = token.strip().lower()
    rows = conn.execute("SELECT id, slug, name FROM axis ORDER BY id").fetchall()
    exact = [r for r in rows if r["slug"] == token]
    if exact:
        return int(exact[0]["id"])
    matches = [
        r for r in rows if token in r["slug"] or token in r["name"].lower()
    ]
    if len(matches) == 1:
        return int(matches[0]["id"])
    if not matches:
        raise ValueError(f"no axis matches {token!r}")
    raise ValueError(
        f"{token!r} is ambiguous: {', '.join(r['slug'] for r in matches)}"
    )


def show_vectors(conn: sqlite3.Connection) -> dict[str, dict[int, int]]:
    """title -> {axis_id: value} for every stored score."""
    vecs: dict[str, dict[int, int]] = {}
    for r in conn.execute(
        "SELECT sh.title AS title, s.axis_id AS axis_id, s.value AS value "
        "FROM score s JOIN show sh ON sh.id = s.show_id"
    ):
        vecs.setdefault(r["title"], {})[int(r["axis_id"])] = int(r["value"])
    return vecs


def _complete(vec: dict[int, int], axis_ids: list[int]) -> bool:
    return all(i in vec for i in axis_ids)


def distance(a: dict[int, int], b: dict[int, int], axis_ids: list[int]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in axis_ids))


def nearest(
    conn: sqlite3.Connection,
    title: str,
    n: int = 5,
    allowed: set[str] | None = None,
) -> list[tuple[str, float, dict[int, int]]]:
    """Return the n nearest shows to `title`, as (title, distance, vector).

    `allowed`, if given, restricts candidates to those titles (e.g. one genre).
    """
    axis_ids, _ = axis_index(conn)
    vecs = show_vectors(conn)
    if title not in vecs:
        raise KeyError(f"{title!r} is not in the DB")
    if not _complete(vecs[title], axis_ids):
        raise ValueError(f"{title!r} has an incomplete score vector")
    target = vecs[title]
    scored = [
        (t, distance(target, v, axis_ids), v)
        for t, v in vecs.items()
        if t != title and _complete(v, axis_ids) and (allowed is None or t in allowed)
    ]
    scored.sort(key=lambda x: x[1])
    return scored[:n]


def nearest_to_vector(
    conn: sqlite3.Connection,
    target: dict[int, float],
    n: int,
    exclude: set[str],
    allowed: set[str] | None = None,
) -> list[tuple[str, float, dict[int, int]]]:
    """Shows nearest to an arbitrary target vector, excluding `exclude` titles."""
    axis_ids, _ = axis_index(conn)
    scored = [
        (t, math.sqrt(sum((target[i] - v[i]) ** 2 for i in axis_ids)), v)
        for t, v in show_vectors(conn).items()
        if t not in exclude
        and _complete(v, axis_ids)
        and (allowed is None or t in allowed)
    ]
    scored.sort(key=lambda x: x[1])
    return scored[:n]


def recommend(
    conn: sqlite3.Connection,
    positives: dict[str, float],
    n: int = 10,
    allowed: set[str] | None = None,
    negatives: list[str] | None = None,
    beta: float = 0.5,
    axis_pushes: dict[int, float] | None = None,
    exclude_extra: set[str] | None = None,
) -> tuple[list[str], list[str], dict[int, float], list[tuple[str, float, dict[int, int]]]]:
    """Recommend from a *weighted* taste profile, pushed away from negatives.

    `positives` maps a liked title to an affinity weight (e.g. Loved 2, Liked 1,
    Fine 0.4); the taste point is the weight-weighted centroid of those shows.
    `negatives` (e.g. "not for me") shift the query away from their centroid
    (Rocchio): target = C_like + beta*(C_like - C_neg), clamped to [0, 10].

    `axis_pushes` maps an axis id to a signed additive nudge (e.g. from
    "why I bounced" complaints — "too slow" pushes Propulsion up), applied
    per-axis *after* the Rocchio shift so it steers only the named axes.
    `exclude_extra` drops further titles from the candidate pool (e.g. shows
    already finished or abandoned via watch-state) without moving the target.

    Returns (recognised positives, recognised negatives, query vector, recommendations).
    """
    axis_ids, _ = axis_index(conn)
    vecs = show_vectors(conn)
    pos = [
        (t, w) for t, w in positives.items()
        if w > 0 and t in vecs and _complete(vecs[t], axis_ids)
    ]
    if not pos:
        raise ValueError("none of the liked shows are in the DB")
    neg = [t for t in (negatives or []) if t in vecs and _complete(vecs[t], axis_ids)]

    wsum = sum(w for _, w in pos)
    c_like = {i: sum(w * vecs[t][i] for t, w in pos) / wsum for i in axis_ids}
    if neg:
        c_neg = {i: sum(vecs[t][i] for t in neg) / len(neg) for i in axis_ids}
        target = {
            i: c_like[i] + beta * (c_like[i] - c_neg[i]) for i in axis_ids
        }
    else:
        target = dict(c_like)

    if axis_pushes:
        for i in axis_ids:
            target[i] += axis_pushes.get(i, 0.0)
    target = {i: min(10.0, max(0.0, target[i])) for i in axis_ids}

    exclude = set(positives) | set(negatives or []) | (exclude_extra or set())
    recs = nearest_to_vector(conn, target, n, exclude=exclude, allowed=allowed)
    return [t for t, _ in pos], neg, target, recs


def parse_constraint(expr: str, conn: sqlite3.Connection) -> tuple[int, str, int]:
    """Parse 'sweep>=8' -> (axis_id, op, value)."""
    for op in _OPS:  # dicts preserve insertion order; longest ops first
        if op in expr:
            token, _, raw = expr.partition(op)
            return resolve_axis(token, conn), op, int(raw.strip())
    raise ValueError(f"no comparison operator in {expr!r} (use >=, <=, >, <, =)")


def query(
    conn: sqlite3.Connection, constraints: list[tuple[int, str, int]]
) -> list[tuple[str, dict[int, int]]]:
    """Shows whose vector satisfies every (axis_id, op, value) constraint."""
    axis_ids, _ = axis_index(conn)
    out = []
    for title, v in show_vectors(conn).items():
        if not _complete(v, axis_ids):
            continue
        if all(_OPS[op](v[aid], val) for aid, op, val in constraints):
            out.append((title, v))
    out.sort(key=lambda x: x[0])
    return out
