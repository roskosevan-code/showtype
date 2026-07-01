# Where we left off

Quick resume note (last updated after round-4 validation slice folded in).

## State of the project

- **Catalog: 957 shows** (753 base + the 204-title round-4 validation slice), each with
  8 descriptive axis scores, ≥1 genre, and a quality layer (execution score 0–10 + reason,
  summary, approx episode/season counts).
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

## Round 4 — catalog expansion (in progress)

- **Validation slice (204 titles, `scripts/catalog-shows-4-val.txt`): DONE.** Submitted as
  3 Batches-API jobs (scores/genres/quality). The `succeeded` counter sat at 0 for 90 min —
  that's the Batches API committing results in bulk at the end, **not** a stall. Cancelling
  the jobs *flushed* the already-completed results (201/202/196 of 204 succeeded). Recovered
  by identifying each batch (custom_id prefix: `sh`=scores, `g`=genres, `q`=quality) and
  running `scripts/fetch_batches.py`. The 8/2/3 canceled stragglers were live-patched
  (`messages.create`, reusing `params()` from the batch scripts). All three passes now
  204/204; DB scores exported back to `docs/catalog-scores.csv` via `export-catalog`.
  Lesson: **don't panic at 0 succeeded — let batches end, or cancel to force a flush.**
- **Main expansion (1110 titles after dedup, `scripts/catalog-shows-4.txt`): SUBMITTED,
  in flight.** 906 new per pass (204 validation titles skipped). Batch IDs recorded in
  `docs/round4-main-batches.json` (scores/genres/quality). **To resume:** poll them, then
  `python3 scripts/fetch_batches.py --file scripts/catalog-shows-4.txt --scores <id>
  --genres <id> --quality <id>`, live-patch any canceled/failed stragglers, then
  `export-catalog` + `build_static.py`. Submitted via `scripts/submit_batches.py` (submit +
  record IDs only, no block-poll). Note `build_quality.py`/`classify_genres.py` are
  batch-only (no live flag); scores have a live path (`score-all`).

## Next up — ideas (nothing agreed yet)

- A dedicated **watchlist view** (currently surfaced only via the toggle + a count line).
- Tune the push magnitudes (±1.5 step, ±3 cap) against real usage.
- Bigger: grow the catalog past 753, or publish the offline HTML (e.g. GitHub Pages).

Design principle settled: **user thinks in words, engine thinks in weights**; keep ≤5
options at the top level and push richer vocabulary one layer down (progressive disclosure).

## Loose end

- ⚠️ **Rotate the API key (again).** The original key was pasted into chat and used for the
  early batches. A fresh key was created for the round-4 recovery — but it was *also* pasted
  into chat, so it's exposed too. Rotate it at console.anthropic.com and disable the old one.
  Nothing in the repo stores any key.
