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

## Next up — ideas (nothing agreed yet)

- Polish/UX pass on the new watch-state controls (7 tiny buttons per row is a lot — could
  hide watch-state behind a disclosure, or a compact menu).
- A dedicated **watchlist view** (currently surfaced only via the toggle + a count line).
- Possibly let "why I bounced" reasons attach to 🚪 bounced shows even without a 👎 (the
  engine already honours reasons on `dropped` shows; the chip editor only shows on 👎).
- Tune the push magnitudes (±1.5 step, ±3 cap) against real usage.

Design principle settled: **user thinks in words, engine thinks in weights**; keep ≤5
options at the top level and push richer vocabulary one layer down (progressive disclosure).

## Loose end

- ⚠️ **Rotate the API key.** It was pasted into the chat early and used for all the
  scoring/genre/quality batches; treat it as exposed and regenerate it at
  console.anthropic.com. Nothing in the repo stores it.
