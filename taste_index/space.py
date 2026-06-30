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
    conn: sqlite3.Connection, title: str, n: int = 5
) -> list[tuple[str, float, dict[int, int]]]:
    """Return the n nearest shows to `title`, as (title, distance, vector)."""
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
        if t != title and _complete(v, axis_ids)
    ]
    scored.sort(key=lambda x: x[1])
    return scored[:n]


def nearest_to_vector(
    conn: sqlite3.Connection,
    target: dict[int, float],
    n: int,
    exclude: set[str],
) -> list[tuple[str, float, dict[int, int]]]:
    """Shows nearest to an arbitrary target vector, excluding `exclude` titles."""
    axis_ids, _ = axis_index(conn)
    scored = [
        (t, math.sqrt(sum((target[i] - v[i]) ** 2 for i in axis_ids)), v)
        for t, v in show_vectors(conn).items()
        if t not in exclude and _complete(v, axis_ids)
    ]
    scored.sort(key=lambda x: x[1])
    return scored[:n]


def recommend(
    conn: sqlite3.Connection, liked: list[str], n: int = 10
) -> tuple[list[str], dict[int, float], list[tuple[str, float, dict[int, int]]]]:
    """Recommend from a taste profile = centroid of the liked shows' vectors.

    Returns (recognised liked titles, centroid vector, recommendations).
    """
    axis_ids, _ = axis_index(conn)
    vecs = show_vectors(conn)
    present = [t for t in liked if t in vecs and _complete(vecs[t], axis_ids)]
    if not present:
        raise ValueError("none of the liked shows are in the DB")
    centroid = {i: sum(vecs[t][i] for t in present) / len(present) for i in axis_ids}
    recs = nearest_to_vector(conn, centroid, n, exclude=set(liked))
    return present, centroid, recs


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
