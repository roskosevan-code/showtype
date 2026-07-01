# Where we left off

Quick resume note (last updated after Phase 4 ②③).

## State of the project

- **Catalog: 753 shows**, each with 8 descriptive axis scores, ≥1 genre, and a quality
  layer (execution score 0–10 + reason, summary, approx episode/season counts).
- **Data files** (all committed; the DB is rebuilt from these):
  - `docs/rubric.md` — the 8-axis rubric (source of truth)
  - `docs/catalog-scores.csv` — 753 shows × 8 axes
  - `docs/genres.csv` — `show,genre,rank` (curated 231 + model-classified 522)
  - `docs/quality.csv` — quality / summary / episodes / seasons
  - `docs/baseline-scores.csv` — 30-show diff reference
- **App** (`taste_index/`): SQLite + retrieval (`space.py`) + zero-dep web UI (`web.py`).
  `python3 -m taste_index serve` auto-builds the DB from the CSVs and serves the UI.
- **Offline UI**: `docs/taste-index.html` (self-contained, ~2.1 MB) — rebuild with
  `python3 scripts/build_static.py`.

## Phases done

- **Phase 0** — rubric sanity-check spike.
- **Phase 1** — scoring pipeline; rubric self-corrected 3× from diff data.
- **Phase 2** — retrieval, recommendation, multi-genre filtering, web UI, offline build.
- **Phase 3** — quality layer (model-judged).
- **Phase 4 ①** — graded reactions (❤ loved / 👍 liked / 😐 fine / 👎 not-for-me) →
  *weighted* recommendation centroid (Loved 2, Liked 1, Fine 0.4) + Rocchio push from
  not-for-me; reactions persist in `localStorage`.
- **Phase 4 ②** — watch-state, separate from affinity: 🔖 watchlist / 👁 seen /
  🚪 bounced (haven't-seen = unset), stored in `localStorage` (`ti-watch`). Seen &
  bounced are **excluded** from recommendations; a "From my watchlist only" toggle
  restricts recs to your watchlist (intersected with any genre filter). Engine hooks:
  `space.recommend(exclude_extra=…)` + `/api/recommend?seen=…&only=…`.
- **Phase 4 ③** — "why I bounced" chips on every 👎 show (`ti-reasons`): 6 everyday
  complaints → *masked per-axis* pushes (Too slow → Propulsion↑ · Hard to follow →
  Density↓ · Couldn't connect → Interiority↑ · Too try-hard → Authorial↓ · Didn't buy
  it → Verisimilitude↑ · Too corny → Register↓ + Verisimilitude↑). Each complaint nudges
  its axis by ±1.5, summed across reasoned shows and capped at ±3 per axis; a reasoned 👎
  steers via these targeted pushes *instead of* the blunt Rocchio centroid. Engine hook:
  `space.recommend(axis_pushes=…)` + `/api/recommend?push=axisId,delta`.

Both are mirrored in the offline build (`scripts/build_static.py` → `docs/taste-index.html`);
served + offline centroids verified identical.

## Polish done (after ②③)

- **#1 Row de-clutter.** The three watch-state buttons collapsed into a single `▾`
  disclosure per row (shows the chosen state's icon in accent colour when set; reveals
  the three options on click). Rows went from ~7 controls to ~5.
- **#3 Reasons on bounced.** 🚪 bounced shows now appear as chips in the taste panel even
  without a 👎, each with the "why I bounced" editor; their reasons feed the axis pushes
  and they're excluded from recs. (Engine already honoured `dropped` reasons.)

## Next up — ideas (nothing agreed yet)

- A dedicated **watchlist view** (currently surfaced only via the toggle + a count line).
- Tune the push magnitudes (±1.5 step, ±3 cap) against real usage.
- Bigger: grow the catalog past 753, or publish the offline HTML (e.g. GitHub Pages).

Design principle settled: **user thinks in words, engine thinks in weights**; keep ≤5
options at the top level and push richer vocabulary one layer down (progressive disclosure).

## Loose end

- ⚠️ **Rotate the API key.** It was pasted into the chat early and used for all the
  scoring/genre/quality batches; treat it as exposed and regenerate it at
  console.anthropic.com. Nothing in the repo stores it.
