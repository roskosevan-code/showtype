# Phase 2 — Use the Coordinates

Phase 1 built the coordinate system (eight descriptive axes) and a way to place
shows in it (scorer + DB). Phase 2 is about **using those coordinates**: turning
the eight-axis vectors into retrieval — similarity and profile search — and
scaling the catalog so the space is dense enough to be useful.

The key property: the eight rubric axes already *are* an interpretable 0–10 vector
space. Similarity is just distance in that space — no embeddings, no extra model.

## Done — retrieval layer

- `showtype/space.py`: vectors, Euclidean distance, k-NN, and profile query.
- `showtype similar "<show>" [-n N]` — nearest shows in taste-space.
- `showtype query --where "sweep>=8" --where "register<=4"` — filter by axis profile
  (axis tokens resolve by slug or substring: `sweep`, `auth`, `veris`, …).

Both run over the stored scores with no API call. Sanity checks hold: The Wire's
nearest neighbour is We Own This City (the other Simon Baltimore systems show);
Breaking Bad's are Happy Valley / Ozark / Better Call Saul (propulsive crime).

## Scaling the catalog

Retrieval is only as good as the catalog is dense. Two ways to grow it:

```bash
showtype score-all   --file shows.txt --skip-existing      # sequential, full price
showtype score-batch --file shows.txt --skip-existing      # Batches API: 50% cost, async
```

`score-batch` submits all requests to the Claude **Batches API**, polls until the
batch ends, then loads the results — the right tool for a few-hundred-show run.
`scripts/catalog-shows.txt` is a starter list of ~90 shows spanning the axis space.

**Done — 231-show catalog.** Two `score-batch` rounds (94/94 then 107/107 succeeded,
from `scripts/catalog-shows.txt` and `catalog-shows-2.txt`) built a 231-show catalog,
committed at `docs/catalog-scores.csv`. Load it without re-spending:

```bash
showtype init-db && showtype backfill --csv docs/catalog-scores.csv
showtype similar "The Bear" -n 6
```

At this density, nearest-neighbour distances tighten to ~2.8–4 (real matches) from
the 5–8 of the sparse 30-show space.

## Done — recommendation engine + web UI

- `space.recommend(liked, n, disliked=...)`: a **taste profile** is the centroid of the
  liked shows' vectors; recommendations are the nearest shows to it (excluding the inputs).
  Liking The Wire + Chernobyl + The Americans surfaces the David Simon canon
  (The Deuce, Show Me a Hero, We Own This City, Generation Kill) purely from axis geometry.
  **Disliked shows** push the query point away from their centroid (Rocchio relevance
  feedback: `target = C_like + 0.5*(C_like - C_dislike)`, clamped to [0,10]) — liking
  The Expanse + BSG but disliking Black Mirror shifts the recs toward bigger, grounded
  systems shows (Andor, ZeroZeroZero, Chernobyl).
- `showtype/web.py` + `showtype serve`: a zero-dependency web UI (stdlib
  `http.server`) — explore a show's axis profile and nearest neighbours, recommend from
  shows you like (and away from shows you don't), and **filter by axis profile** with
  min/max sliders per axis. JSON API at `/api/meta`, `/api/show`, `/api/similar`,
  `/api/recommend`, `/api/query`.

## Done — genre tags

The axes are *structural*, so taste-space encodes structure, not genre/humour — a comedy
and a drama with the same fingerprint sit together. `docs/genres.csv` (`show,genre,rank`)
adds genres as categorical metadata: a `show_genre` junction table (rank 0 = primary,
denormalized to `show.genre`) holds **one or more genres per show** — Barry is Comedy *and*
Crime, so it appears under both filters. Loaded with `tag-genres`; `similar` / `recommend`
take an optional genre filter (membership, any rank). Liking Fleabag + Atlanta + Barry
recommends prestige dramas unfiltered, but Russian Doll / BoJack / PEN15 / Master of None
when constrained to Comedy. The web UI exposes "same genre only" (explore, unions the
target's genres) and a genre dropdown (recommend).

## Deferred

- **Quality layer** — the rubric notes axes are descriptive and "quality is tracked
  separately." A separate quality/rating dimension (and a user taste-profile to match
  against) is the natural Phase 3.
