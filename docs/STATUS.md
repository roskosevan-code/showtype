# Where we left off

Quick resume note (last updated after round-4 completed: catalog at 1863).

## State of the project

- **Catalog: 1863 shows** (753 base + 204 round-4 validation + 906 round-4 main expansion),
  each with 8 descriptive axis scores, ≥1 genre, and a quality layer (execution score 0–10 +
  reason, summary, approx episode/season counts).
- **Data files** (all committed; the DB is rebuilt from these):
  - `docs/rubric.md` — the 8-axis rubric (source of truth)
  - `docs/catalog-scores.csv` — 753 shows × 8 axes
  - `docs/genres.csv` — `show,genre,rank` (curated 231 + model-classified 522)
  - `docs/quality.csv` — quality / summary / episodes / seasons
  - `docs/baseline-scores.csv` — 30-show diff reference
- **App** (`showtype/`): SQLite + retrieval (`space.py`) + zero-dep web UI (`web.py`).
  `python3 -m showtype serve` auto-builds the DB from the CSVs and serves the UI.
- **Offline UI**: `docs/showtype.html` (self-contained, ~5.1 MB) — rebuild with
  `python3 scripts/build_static.py`.

## Phases done

- **Phase 0** — rubric sanity-check spike.
- **Phase 1** — scoring pipeline; rubric self-corrected 3× from diff data.
- **Phase 2** — retrieval, recommendation, multi-genre filtering, web UI, offline build.
- **Phase 3** — quality layer (model-judged).
- **Phase 4 ①** — a single **affinity ranking**, best → worst: ❤ loved (w2) / 👍 liked (w1) /
  🙅 never-interested / ⏹️ started-&-stopped. Loved+liked form the *weighted* centroid;
  the two negatives push away (Rocchio) — never-interested is always blunt, started-&-stopped
  steers via reason-code axis pushes when reasoned (else blunt). Everything ranked (and 👁 seen)
  is excluded from recs. Persists in `localStorage`; a load-time migration folds the old
  😐 fine (dropped) and 🚪 bounced watch-state into this scale. *(Superseded the original
  ❤/👍/😐/👎 + separate 🚪-bounced watch-state; the retired weight was Fine 0.4.)*
- **Phase 4 ②** — watch-state, separate from affinity: 🔖 watchlist / 👁 seen
  (haven't-seen = unset), stored in `localStorage` (`ti-watch`). *(🚪 bounced moved into the
  ① ranking as ⏹️ started-&-stopped.)* Seen is **excluded** from recommendations; a
  "From my watchlist only" toggle
  restricts recs to your watchlist (intersected with any genre filter). Engine hooks:
  `space.recommend(exclude_extra=…)` + `/api/recommend?seen=…&only=…`.
- **Phase 4 ③** — "why I bounced" chips on every ⏹️ started-&-stopped show (`ti-reasons`),
  the only ranking level that elicits reasons: 6 everyday
  complaints → *masked per-axis* pushes (Too slow → Propulsion↑ · Hard to follow →
  Density↓ · Couldn't connect → Interiority↑ · Too try-hard → Authorial↓ · Didn't buy
  it → Verisimilitude↑ · Too corny → Register↓ + Verisimilitude↑). Each complaint nudges
  its axis by ±1.5, summed across reasoned shows and capped at ±3 per axis; a reasoned 👎
  steers via these targeted pushes *instead of* the blunt Rocchio centroid. Engine hook:
  `space.recommend(axis_pushes=…)` + `/api/recommend?push=axisId,delta`.

Both are mirrored in the offline build (`scripts/build_static.py` → `docs/showtype.html`);
served + offline centroids verified identical.

## Polish done (after ②③)

- **#1 Row de-clutter.** The three watch-state buttons collapsed into a single `▾`
  disclosure per row (shows the chosen state's icon in accent colour when set; reveals
  the three options on click). Rows went from ~7 controls to ~5.
- **#3 Reasons on bounced.** 🚪 bounced shows now appear as chips in the taste panel even
  without a 👎, each with the "why I bounced" editor; their reasons feed the axis pushes
  and they're excluded from recs. (Engine already honoured `dropped` reasons.)

## Phase 5 — mobile-first UI redesign (2026-07-04)

- **New layout:** three tabs — Explore / For You / Browse — with a fixed bottom tab bar on
  mobile (pill nav on desktop ≥760px). Rows are now clean, full-width tap targets (title +
  genres + Q + distance); tapping any row opens a **bottom sheet** (centered modal on
  desktop) with the summary, big segmented ranking/watch buttons, "why didn't it land"
  chips, and taste-profile bars. Custom search typeahead replaced `<datalist>`.
  Browse filters auto-apply (debounced) instead of needing an Apply button. Same warm
  dark palette, refined (16px base font, safe-area insets, 44px+ touch targets).
- **De-duplicated the two builds:** `web.py` now exposes `PAGE_HEAD` (CSS+markup),
  `SERVED_ENGINE_JS` (fetch adapters), and `UI_JS` (all rendering/state/events, shared).
  `build_static.py` swaps in a local-compute `ENGINE` with the same 5-method interface
  (meta/show/similar/recommend/query) and reuses PAGE_HEAD + UI_JS verbatim — UI changes
  now land once instead of twice. Behavior (weights, Rocchio, pushes, migration of old
  localStorage keys) is unchanged; storage keys still `ti-reactions`/`ti-watch`/`ti-reasons`.

## Round 4 — catalog expansion (complete)

- **Validation slice (204 titles, `scripts/catalog-shows-4-val.txt`): DONE.** Submitted as
  3 Batches-API jobs (scores/genres/quality). The `succeeded` counter sat at 0 for 90 min —
  that's the Batches API committing results in bulk at the end, **not** a stall. Cancelling
  the jobs *flushed* the already-completed results (201/202/196 of 204 succeeded). Recovered
  by identifying each batch (custom_id prefix: `sh`=scores, `g`=genres, `q`=quality) and
  running `scripts/fetch_batches.py`. The 8/2/3 canceled stragglers were live-patched
  (`messages.create`, reusing `params()` from the batch scripts). All three passes now
  204/204; DB scores exported back to `docs/catalog-scores.csv` via `export-catalog`.
  Lesson: **don't panic at 0 succeeded — let batches end, or cancel to force a flush.**
- **Main expansion (1110 titles, `scripts/catalog-shows-4.txt`): DONE.** 906 new per pass.
  Batches sat at 0-succeeded again; cancel-to-flush recovered ~95% (865/873/864 of 906), and
  the 41/33/45 canceled/failed stragglers were live-patched — all three passes now 1110/1110.
  Batch IDs are in `docs/round4-main-batches.json`. Dropped 3 orphan quality rows (garbled/
  non-catalog `show` names from `_resolve` fallback) to restore CSV parity (all three = 1863).
- **Fixed a latent offline-build bug:** `scripts/build_static.py:ensure_db` used to skip
  genres/quality loading whenever the `show` table was non-empty — but scores get written to
  the DB directly (score-all/fetch_batches) while genres+quality land only in the CSVs, so
  new shows shipped with empty genres/null quality. Now it always reloads all CSVs (loaders
  are idempotent). The pre-fix 957-show HTML had this gap too.

## Next up — ideas (nothing agreed yet)

- A dedicated **watchlist view** (currently surfaced only via the toggle + a count line).
- Tune the push magnitudes (±1.5 step, ±3 cap) against real usage.
- Bigger: a round-5 catalog expansion past 1863, or publish the offline HTML (e.g. GitHub
  Pages — note it's ~5.1 MB now, so size is worth a thought first).

Design principle settled: **user thinks in words, engine thinks in weights**; keep ≤5
options at the top level and push richer vocabulary one layer down (progressive disclosure).
