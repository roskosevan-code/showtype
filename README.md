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

**Next:** review the output against your own read of these shows (the gate). If it holds
up, proceed to Phase 1.

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
  phase0-scores.csv             # (generated) Phase 0 scores, 240 rows
scripts/
  gen_phase0.py                 # Source of truth for the two phase0 files; re-run to regenerate
```
