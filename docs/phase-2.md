# Phase 2 — Use the Coordinates

Phase 1 built the coordinate system (eight descriptive axes) and a way to place
shows in it (scorer + DB). Phase 2 is about **using those coordinates**: turning
the eight-axis vectors into retrieval — similarity and profile search — and
scaling the catalog so the space is dense enough to be useful.

The key property: the eight rubric axes already *are* an interpretable 0–10 vector
space. Similarity is just distance in that space — no embeddings, no extra model.

## Done — retrieval layer

- `taste_index/space.py`: vectors, Euclidean distance, k-NN, and profile query.
- `taste-index similar "<show>" [-n N]` — nearest shows in taste-space.
- `taste-index query --where "sweep>=8" --where "register<=4"` — filter by axis profile
  (axis tokens resolve by slug or substring: `sweep`, `auth`, `veris`, …).

Both run over the stored scores with no API call. Sanity checks hold: The Wire's
nearest neighbour is We Own This City (the other Simon Baltimore systems show);
Breaking Bad's are Happy Valley / Ozark / Better Call Saul (propulsive crime).

## Scaling the catalog

Retrieval is only as good as the catalog is dense. Two ways to grow it:

```bash
taste-index score-all   --file shows.txt --skip-existing   # sequential, full price
taste-index score-batch --file shows.txt --skip-existing   # Batches API: 50% cost, async
```

`score-batch` submits all requests to the Claude **Batches API**, polls until the
batch ends, then loads the results — the right tool for a few-hundred-show run.
`scripts/catalog-shows.txt` is a starter list of ~90 shows spanning the axis space.

**Done — 231-show catalog.** Two `score-batch` rounds (94/94 then 107/107 succeeded,
from `scripts/catalog-shows.txt` and `catalog-shows-2.txt`) built a 231-show catalog,
committed at `docs/catalog-scores.csv`. Load it without re-spending:

```bash
taste-index init-db && taste-index backfill --csv docs/catalog-scores.csv
taste-index similar "The Bear" -n 6
```

At this density, nearest-neighbour distances tighten to ~2.8–4 (real matches) from
the 5–8 of the sparse 30-show space.

## Done — recommendation engine + web UI

- `space.recommend(liked, n)`: a **taste profile** is the centroid of the liked shows'
  vectors; recommendations are the nearest shows to that centroid (excluding the inputs).
  Liking The Wire + Chernobyl + The Americans surfaces the David Simon canon
  (The Deuce, Show Me a Hero, We Own This City, Generation Kill) purely from axis geometry.
- `taste_index/web.py` + `taste-index serve`: a zero-dependency web UI (stdlib
  `http.server`) — explore a show's axis profile and nearest neighbours, and recommend
  from shows you like. JSON API at `/api/meta`, `/api/show`, `/api/similar`, `/api/recommend`.

## Deferred

- **Quality layer** — the rubric notes axes are descriptive and "quality is tracked
  separately." A separate quality/rating dimension (and a user taste-profile to match
  against) is the natural Phase 3.
