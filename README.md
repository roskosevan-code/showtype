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

**Phase 1 — Data model + scoring pipeline (in progress).** A SQLite data model
(`axis` / `show` / `score`) whose `axis` table is seeded *verbatim* from
`docs/rubric.md`, plus a scorer that rates a show on all eight axes via the Claude
API (Claude Opus 4.8, adaptive thinking, structured outputs). See **Usage** below.

## Usage (Phase 1)

```bash
pip install -e .                      # installs anthropic + pydantic
python -m taste_index init-db         # create taste_index.db, seed the 8 axes from docs/rubric.md
python -m taste_index axes            # list the seeded axes
python -m taste_index backfill        # load the baseline scores (docs/baseline-scores.csv) into the DB

export ANTHROPIC_API_KEY=sk-ant-...   # required for scoring
python -m taste_index score "The Wire"   # score one show via the Claude API, store the result
python -m taste_index show "The Wire"    # print stored scores for a show
python -m taste_index diff "The Wire" "Severance"   # re-score live, diff vs the stored baseline (no save)
```

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
scripts/
  gen_phase0.py                 # Source of truth for the two phase0 files; re-run to regenerate
  refresh_baseline.py           # Re-score the gold set -> docs/baseline-scores.csv (run after rubric edits)
taste_index/                    # Phase 1 package
  rubric.py                     # parse the 8 axes out of docs/rubric.md
  schema.sql                    # axis / show / score tables
  db.py                         # SQLite access layer
  scorer.py                     # Claude-API scorer (structured outputs)
  cli.py                        # init-db / axes / score / show
pyproject.toml                  # package metadata + deps (anthropic, pydantic)
```
