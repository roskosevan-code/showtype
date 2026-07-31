# Show Type

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

**Phase 2 — Use the coordinates (complete).** The eight axes already form an
interpretable vector space, so similarity is just distance in it. `similar` returns a
show's nearest neighbours and `query` filters by axis profile — both over the stored
scores, no API call. Also brought recommendation, multi-genre filtering, the web UI, and
the offline build. See [`docs/phase-2.md`](docs/phase-2.md).

**Phase 3 — Quality layer (complete).** A model-judged execution score kept separate from
the descriptive axes. See **Quality layer** below.

**Phase 4 — Reactions (complete).** A single affinity ranking drives recommendation,
watch-state is tracked separately, and "why didn't it land" reasons steer the result on
specific axes. See **The web UI** below.

**Phase 5 — Mobile-first UI (complete).** Three tabs (Explore / For You / Browse) with a
bottom sheet for detail, and the served and offline builds de-duplicated onto one shared
UI layer.

**Catalog: 1863 shows**, each with 8 axis scores, ≥1 genre, and a quality row.

[`docs/STATUS.md`](docs/STATUS.md) is the resume note — current state, what's next, and
the lessons worth keeping. It's more current than this file; when the two disagree, trust
STATUS.

## Usage

```bash
pip install -e .                      # installs anthropic + pydantic
python -m showtype init-db            # create showtype.db, seed the 8 axes from docs/rubric.md
python -m showtype axes               # list the seeded axes
python -m showtype backfill           # load the baseline scores (docs/baseline-scores.csv) into the DB

export ANTHROPIC_API_KEY=sk-ant-...   # required for scoring
python -m showtype score "The Wire"      # score one show via the Claude API, store the result
python -m showtype score-all "Succession" "Mad Men" --skip-existing      # score new shows (sequential)
python -m showtype score-batch --file scripts/catalog-shows.txt --skip-existing     # scale via Batches API (50% cost)
python -m showtype show "The Wire"       # print stored scores for a show
python -m showtype diff "The Wire" "Severance"      # re-score live, diff vs the stored baseline (no save)

# Phase 2 — retrieval over the 8-axis space (no API calls):
python -m showtype similar "The Wire" -n 5                             # nearest shows in taste-space
python -m showtype query --where "sweep>=8" --where "register<=4"      # filter by axis profile
python -m showtype tag-genres                                          # load genres (docs/genres.csv)
python -m showtype serve                                               # web UI at http://127.0.0.1:8000
```

**Optional PostgreSQL backend.** By default everything runs on SQLite (zero
dependencies). Set `DATABASE_URL` and the same commands run against PostgreSQL instead
(via psycopg v3, imported only on that path): `pip install -e '.[postgres]'`, `export
DATABASE_URL=postgresql://…`, then `python -m showtype db-load` populates Postgres
from the committed CSVs in one step. The offline `scripts/build_static.py` output stays
SQLite/zero-dependency regardless. Details in [`docs/postgres.md`](docs/postgres.md).

**Just want the UI?** `python -m showtype serve` auto-builds the database from the
committed CSVs on first run — so from a fresh clone it's a single command, no API key and
no dependencies (the UI is pure standard library). Then open <http://127.0.0.1:8000>.

**No Python at all?** `docs/showtype.html` is a single self-contained file (all 1863
shows baked in; similarity/recommendation/filter reimplemented in client-side JS) — just
open it in a browser. Rebuild with `python scripts/build_static.py` after the data changes.

The **web UI** (`serve`, stdlib `http.server`, no deps) is three tabs — **Explore** (a
show's axis profile + nearest neighbours), **For You** (recommendations), and **Browse**
(filter by axis profile with min/max sliders per axis, e.g. Sweep 8–10 + Register 0–4 +
Verisimilitude 8–10 → the restrained systems-storytelling cluster). Tapping any row opens
a bottom sheet (a centered modal on desktop ≥760px) with the summary, ranking and
watch-state buttons, reason chips, and the taste profile.

**Affinity** is a single ranking, best → worst: ❤️ loved / 👍 liked / 🙅 never-interested /
⏹️ started-&-stopped. Loved and liked form a *weighted* taste centroid (loved 2×, liked 1×);
the two negatives push away from it (Rocchio). Everything you've ranked is excluded from
recommendations.

**Watch-state** is tracked separately from affinity: 🔖 watchlist or 👁 seen (haven't-seen
is simply unset). Seen shows are never recommended; a "From my watchlist only" toggle ranks
your own watchlist by taste fit.

**"Why didn't it land"** adds six everyday complaints under each ⏹️ started-&-stopped — *too
slow, hard to follow, couldn't connect, too try-hard, didn't buy it, too corny* — each
mapping to a **masked per-axis push** (e.g. "too slow" nudges the Propulsion target up) so a
dislike steers the recommendation on the axes you actually reacted to, not the whole vector.
Each complaint nudges its axis by ±1.5, summed across shows and capped at ±3 per axis; a
reasoned dislike steers via these targeted pushes *instead of* the blunt centroid.
Started-&-stopped is the only level that elicits reasons — never-interested is always blunt.

All three (`ti-reactions` / `ti-watch` / `ti-reasons`) persist in `localStorage` and are
mirrored in the offline build.

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
  catalog-scores.csv            # (generated) 1863-show catalog for retrieval; load with `backfill --csv`
  genres.csv                    # show,genre,rank — one or more genres per show; load with `tag-genres`
  quality.csv                   # (generated) model-judged quality + summary + episodes; load with `load-quality`
  postgres.md                   # optional PostgreSQL backend: setup, db-load, parity tests
  showtype.html                 # (generated) self-contained offline UI; open in any browser
scripts/
  gen_phase0.py                 # Source of truth for the two phase0 files; re-run to regenerate
  refresh_baseline.py           # Re-score the gold set -> docs/baseline-scores.csv (run after rubric edits)
  gen_genres.py                 # Author/validate docs/genres.csv (genre buckets -> flat CSV)
  build_static.py               # Bake the catalog into a self-contained docs/showtype.html
  classify_genres.py            # Batches-API genre classifier for bulk-added shows
  build_quality.py              # Batches-API quality/summary/episode pass -> docs/quality.csv
showtype/                       # Phase 1 package
  rubric.py                     # parse the 8 axes out of docs/rubric.md
  schema.sql                    # axis / show / score tables (SQLite)
  schema_pg.sql                 # same schema for PostgreSQL (used when DATABASE_URL is set)
  db.py                         # dual-backend DB access layer (SQLite default, Postgres via psycopg)
  scorer.py                     # Claude-API scorer (structured outputs)
  space.py                      # taste-space retrieval: k-NN, profile query, recommend (centroid)
  web.py                        # zero-dependency web UI (http.server) + JSON API
  cli.py                        # init-db / db-load / backfill / score* / diff / similar / query / serve / show
tests/
  test_backends.py              # SQLite invariants + SQLite/Postgres parity (PG cases skip w/o DATABASE_URL)
pyproject.toml                  # package metadata + deps (anthropic, pydantic; optional [postgres] extra)
LICENSE                         # MIT — covers the code and the generated data files alike
```

## License and provenance

MIT — see [`LICENSE`](LICENSE). This covers the code and the generated data files alike.

The axis scores, genre labels, and quality ratings in `docs/*.csv` are **generated by
Claude** against the rubric in [`docs/rubric.md`](docs/rubric.md). They are model
characterizations, not human editorial ratings, critic consensus, or measured data. The
rubric has been hand-calibrated and self-corrected three times against a gold set, and the
axes are descriptive rather than evaluative — but treat the numbers as a consistent
machine reading of each show, not as ground truth.
