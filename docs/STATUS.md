# Where we left off

Quick resume note (last updated at commit `40676b8`).

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

## Next up — the user-ranking plan (agreed)

- **② Watchlist + watch-state.** Separate *affinity* (the reactions) from *watch state*
  (finished / didn't-finish / watchlist / haven't-seen). Use watch-state to **filter**:
  never recommend what you've finished, surface watchlist items, exclude no-interest.
  Top-level stays ~4 fast options; watchlist is an orthogonal toggle.
- **③ Axis-targeted "why I bounced" reasons** (the showcase layer). A second-level,
  negative-side-only set of ~6 chips that map to axes and apply *masked per-axis* pushes:
  - Too slow → Propulsion · Hard to follow → Density · Cold/couldn't connect → Interiority
  - Too try-hard → Authorial Signature · Didn't buy it → Verisimilitude · Too corny → Register×Verisimilitude
  (Institutional Sweep and Scope have no natural everyday complaint — steered indirectly.)

Design principle settled: **user thinks in words, engine thinks in weights**; keep ≤5
options at the top level and push richer vocabulary one layer down (progressive disclosure).

## Loose end

- ⚠️ **Rotate the API key.** It was pasted into the chat early and used for all the
  scoring/genre/quality batches; treat it as exposed and regenerate it at
  console.anthropic.com. Nothing in the repo stores it.
