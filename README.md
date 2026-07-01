# The Taste Index

A system for characterizing TV shows along eight descriptive axes, so they can be
located, compared, and routed — not ranked. The axes are *descriptive, not
evaluative*: a score locates a show in taste-space rather than declaring it good or bad
(quality is tracked separately).

## The eight axes

| # | Axis | What it measures |
|---|------|------------------|
| 1 | **Propulsion** | Forward momentum — each scene creating the conditions for the next (not speed or action). |
| 2 | **Scope** | Size of the canvas — geographic, temporal, or social (score the largest). |
| 3 | **Institutional Sweep** | Degree to which a system/institution is the show's real subject. |
| 4 | **Interiority** | How far the show goes inside a consciousness vs. observing behavior. |
| 5 | **Authorial Signature** | Strength and distinctiveness of the authorial hand (loud or quiet). |
| 6 | **Verisimilitude** | How authentic, granular, and lived-in the world feels. |
| 7 | **Density** | How much the show asks of the viewer per minute. |
| 8 | **Register** | Where the show sits on the restrained ↔ operatic spectrum. |

Each axis is an integer 0–10. Full definitions, scoring conventions, calibration
anchors, and worked examples live in [`docs/rubric.md`](docs/rubric.md).

## Status

**Phase 0 — Rubric sanity check.** A validation spike to confirm the rubric produces
sane, useful axis scores by hand, before any pipeline is built. The procedure and exit
criteria are in [`docs/phase-0-claude-code-task.md`](docs/phase-0-claude-code-task.md).

The spike has been **run once** over the 30-show starter gold set:
[`docs/phase0-scores.md`](docs/phase0-scores.md) (per-show tables + Flags) and
[`docs/phase0-scores.csv`](docs/phase0-scores.csv) (240 rows). All 14 calibration-anchor
shows reproduce the rubric's anchor table exactly. Both files are regenerated from a
single source of truth, [`scripts/gen_phase0.py`](scripts/gen_phase0.py), so the table
and CSV never drift — edit the scores there and re-run `python3 scripts/gen_phase0.py`.

**Phase 1 — Data model + scoring pipeline (complete).** A SQLite data model
(`axis` / `show` / `score`) whose `axis` table is seeded *verbatim* from
`docs/rubric.md`, plus a scorer that rates a show on all eight axes via the Claude
API (Claude Opus 4.8, adaptive thinking, structured outputs). The full loop is in
place — seed from rubric → score (single or batch) → diff against a clean baseline →
tighten the rubric → refresh. The diff loop drove three rubric refinements (Register
×2, Institutional Sweep ×1), each verified on the shows that exposed it; the refreshed
baseline agrees with the original hand-scores 96% within one point with no systematic
skew. See **Usage** below.

**Phase 2 — Use the coordinates (in progress).** The eight axes already form an
interpretable vector space, so similarity is just distance in it. `similar` returns a
show's nearest neighbours and `query` filters by axis profile — both over the stored
scores, no API call. Next: scale the catalog with `score-all`. See
[`docs/phase-2.md`](docs/phase-2.md).

## Usage

```bash
pip install -e .                      # installs anthropic + pydantic
python -m taste_index init-db         # create taste_index.db, seed the 8 axes from docs/rubric.md
python -m taste_index axes            # list the seeded axes
python -m taste_index backfill        # load the baseline scores (docs/baseline-scores.csv) into the DB

export ANTHROPIC_API_KEY=sk-ant-...   # required for scoring
python -m taste_index score "The Wire"   # score one show via the Claude API, store the result
python -m taste_index score-all "Succession" "Mad Men" --skip-existing   # score new shows (sequential)
python -m taste_index score-batch --file scripts/catalog-shows.txt --skip-existing  # scale via Batches API (50% cost)
python -m taste_index show "The Wire"    # print stored scores for a show
python -m taste_index diff "The Wire" "Severance"   # re-score live, diff vs the stored baseline (no save)

# Phase 2 — retrieval over the 8-axis space (no API calls):
python -m taste_index similar "The Wire" -n 5                          # nearest shows in taste-space
python -m taste_index query --where "sweep>=8" --where "register<=4"   # filter by axis profile
python -m taste_index tag-genres                                       # load genres (docs/genres.csv)
python -m taste_index serve                                            # web UI at http://127.0.0.1:8000
```

**Just want the UI?** `python -m taste_index serve` auto-builds the database from the
committed CSVs on first run — so from a fresh clone it's a single command, no API key and
no dependencies (the UI is pure standard library). Then open <http://127.0.0.1:8000>.

**No Python at all?** `docs/taste-index.html` is a single self-contained file (all 231
shows baked in; similarity/recommendation/filter reimplemented in client-side JS) — just
open it in a browser. Rebuild with `python scripts/build_static.py` after the data changes.

The **web UI** (`serve`, stdlib `http.server`, no deps) browses a show's axis profile +
nearest neighbours and recommends from your **graded reactions** — react to any show with
❤ loved / 👍 liked / 😐 fine / 👎 not-for-me, and the recommender builds a *weighted*
taste centroid (Loved counts 2×, Liked 1×, Fine 0.4×) pushed away from not-for-me shows
(Rocchio). Reactions persist in `localStorage`. A third panel **filters by axis profile**
with min/max sliders per axis (e.g. Sweep 8–10 + Register 0–4 + Verisimilitude 8–10 → the
restrained systems-storytelling cluster).

**Watch-state** (Phase 4 ②) is tracked separately from affinity: mark a show 🔖 watchlist,
👁 seen, or 🚪 bounced. Seen and bounced shows are never recommended again; a "From my
watchlist only" toggle ranks your own watchlist by taste fit. **"Why I bounced"** (Phase 4
③) adds six everyday complaints under each 👎 — *too slow, hard to follow, couldn't connect,
too try-hard, didn't buy it, too corny* — each mapping to a **masked per-axis push** (e.g.
"too slow" nudges the Propulsion target up) so a dislike steers the recommendation on the
axes you actually reacted to, not the whole vector. Watch-state and reasons persist in
`localStorage` and are mirrored in the offline build.

**Genre tags** (`docs/genres.csv` → `show_genre`, one *or more* genres per show; rank 0 is
primary) are categorical metadata — the axes are *structural*, so they don't encode
genre/humour. Genre filtering closes that gap: liking Fleabag + Atlanta + Barry recommends
prestige dramas across all genres but Russian Doll / BoJack / PEN15 when constrained to
Comedy. Multi-genre means a show appears under each of its genres — Barry (Comedy + Crime)
shows up in both filters. The UI exposes "same genre only" (explore) and a genre dropdown
(recommend).

**Quality layer** (`docs/quality.csv` → `show.quality`/`summary`/`episodes`/`seasons`,
loaded with `load-quality`). The axes are *descriptive*; the rubric keeps quality separate,
so this is a **model-judged execution score (0–10, evaluative)** plus a one-line reason, a
spoiler-free summary, and approximate episode/season counts (model estimates — `≈`, null
when unsure). The UI shows a `Q8` badge on every row, a summary + execution block in the
profile, and a "sort by quality" toggle on recommendations.

**Baselines.** `docs/phase0-scores.csv` is the frozen Phase 0 hand-scored spike (kept
for provenance). `docs/baseline-scores.csv` is the **active diff reference** — the gold
set re-scored by the model under the *current* rubric, regenerated with
`python scripts/refresh_baseline.py` after the rubric changes. `backfill` loads it, and
`diff` compares fresh live scores against it. The current baseline agrees with the
original hand-scores 96% within one point with no systematic skew.

The rubric is the single source of truth: the eight axes are seeded into the `axis`
table and the full rubric text is handed to the scorer as context. Revise
`docs/rubric.md` (not code) when an axis is mis-reading, then re-run `init-db`.

If the scores are largely sane and justifications concrete, proceed to **Phase 1**:
seed an `Axis` table from `docs/rubric.md` and begin building the scoring pipeline. If
specific axes are consistently wrong, revise the axis definitions and anchors in
`docs/rubric.md` and re-run — iterate in the rubric, not in code.

## Layout

```
docs/
  rubric.md                     # The scoring rubric (v1) — the reference + Phase 1 seed
  phase-0-claude-code-task.md   # Phase 0 spike: procedure, gold-set, exit criteria
  phase0-scores.md              # (generated) Phase 0 per-show tables + Flags
  phase0-scores.csv             # (frozen) Phase 0 hand-scored spike, 240 rows
  baseline-scores.csv           # (generated) active diff baseline: gold set re-scored under current rubric
  catalog-scores.csv            # (generated) 753-show catalog for retrieval; load with `backfill --csv`
  genres.csv                    # show,genre,rank — curated (231) + model-classified; load with `tag-genres`
  quality.csv                   # (generated) model-judged quality + summary + episodes; load with `load-quality`
  taste-index.html              # (generated) self-contained offline UI; open in any browser
scripts/
  gen_phase0.py                 # Source of truth for the two phase0 files; re-run to regenerate
  refresh_baseline.py           # Re-score the gold set -> docs/baseline-scores.csv (run after rubric edits)
  gen_genres.py                 # Author/validate docs/genres.csv (genre buckets -> flat CSV)
  build_static.py               # Bake the catalog into a self-contained docs/taste-index.html
  classify_genres.py            # Batches-API genre classifier for bulk-added shows
  build_quality.py              # Batches-API quality/summary/episode pass -> docs/quality.csv
taste_index/                    # Phase 1 package
  rubric.py                     # parse the 8 axes out of docs/rubric.md
  schema.sql                    # axis / show / score tables
  db.py                         # SQLite access layer
  scorer.py                     # Claude-API scorer (structured outputs)
  space.py                      # taste-space retrieval: k-NN, profile query, recommend (centroid)
  web.py                        # zero-dependency web UI (http.server) + JSON API
  cli.py                        # init-db / backfill / score* / diff / similar / query / serve / show
pyproject.toml                  # package metadata + deps (anthropic, pydantic)
```
