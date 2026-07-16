# The Taste Index — working notes

Eight-axis descriptive characterization of TV shows. `README.md` explains the axes and
the CLI; this file covers what the README doesn't say.

**Read `docs/STATUS.md` first** — it's the resume note and is kept current. When it and
the README disagree, STATUS wins.

## Commands

```bash
.venv/bin/python -m pytest -q          # tests — NOT `python3 -m pytest`
python3 -m taste_index serve           # web UI at :8000; auto-builds the DB from CSVs
python3 scripts/build_static.py        # rebuild docs/taste-index.html after data changes
```

`pytest` and `psycopg` live only in `.venv` and are absent from `pyproject.toml`, so the
bare `python3 -m pytest` fails with `No module named pytest`. The Postgres parity cases
skip unless `DATABASE_URL` is set (7 skipped is the normal local result).

## Source-of-truth rules

The generated artifacts are downstream of a single input each. Edit the input, regenerate —
never patch the output.

| Output | Source | Regenerate with |
|---|---|---|
| `axis` table + scorer context | `docs/rubric.md` | `init-db` |
| `docs/phase0-scores.{md,csv}` | `scripts/gen_phase0.py` | `python3 scripts/gen_phase0.py` |
| `docs/baseline-scores.csv` | the rubric + gold set | `python3 scripts/refresh_baseline.py` |
| `docs/catalog-scores.csv` | the DB | `python3 -m taste_index export-catalog` |
| `docs/taste-index.html` | the CSVs | `python3 scripts/build_static.py` |

When an axis mis-reads, revise the definition and anchors in `docs/rubric.md` — not
`scorer.py`. The rubric self-corrected three times this way (Register ×2, Institutional
Sweep ×1). `taste_index.db` is disposable and rebuilt from the committed CSVs.

## Gotchas

**The three catalog CSVs must agree on show count.** `catalog-scores.csv`, `genres.csv`,
and `quality.csv` are all 1863 distinct shows. Round 4 silently broke parity via orphan
`quality` rows from `_resolve` fallback (garbled non-catalog titles). Check after any bulk
add:

```bash
.venv/bin/python -c "
import csv
for f in ('catalog-scores','genres','quality'):
    print(f, len({r['show'] for r in csv.DictReader(open(f'docs/{f}.csv'))}))"
```

**Batches API: `succeeded` stuck at 0 is not a stall.** The API commits results in bulk at
the end, so the counter reads 0 for the whole run (90 min on round 4). Let it finish, or
**cancel to force a flush** — cancelling recovers the already-completed results (~95%).
This has cost real time twice. Recover with `scripts/fetch_batches.py` (custom_id prefixes:
`sh`=scores, `g`=genres, `q`=quality), then live-patch the stragglers via `messages.create`
reusing `params()` from the batch scripts. Batch IDs land in `docs/round4-main-batches.json`.

**Scores and metadata take different paths into the DB.** `score-all`/`fetch_batches.py`
write scores straight to the DB, but genres and quality land only in the CSVs. Anything
reading the DB must reload all three CSVs (the loaders are idempotent) or new shows ship
with empty genres and null quality — this was a real bug in `build_static.py:ensure_db`.

**UI code is shared between the two builds.** `web.py` owns `PAGE_HEAD` (CSS+markup),
`SERVED_ENGINE_JS` (fetch adapters), and `UI_JS` (rendering/state/events);
`build_static.py` reuses `PAGE_HEAD` + `UI_JS` verbatim and swaps in a local-compute
`ENGINE` with the same 5-method interface (meta/show/similar/recommend/query). Edit the UI
once in `web.py` — don't fork the static build. `localStorage` keys are `ti-reactions` /
`ti-watch` / `ti-reasons`.

**Never inline an API key on a command line.** Claude Code persists the literal command
into `.claude/settings.local.json` permission rules, where it lingers in plaintext. Export
`ANTHROPIC_API_KEY` in the shell instead.

## Design principle

**User thinks in words, engine thinks in weights.** Keep ≤5 options at the top level and
push richer vocabulary one layer down (progressive disclosure). The axes are *descriptive*,
never evaluative — quality is a separate layer, and genre is separate categorical metadata.
