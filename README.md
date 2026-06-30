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
Output of the spike will land in `docs/phase0-scores.md` and `docs/phase0-scores.csv`.

If the scores are largely sane and justifications concrete, proceed to **Phase 1**:
seed an `Axis` table from `docs/rubric.md` and begin building the scoring pipeline. If
specific axes are consistently wrong, revise the axis definitions and anchors in
`docs/rubric.md` and re-run — iterate in the rubric, not in code.

## Layout

```
docs/
  rubric.md                     # The scoring rubric (v1) — the reference + Phase 1 seed
  phase-0-claude-code-task.md   # Phase 0 spike: procedure, gold-set, exit criteria
  phase0-scores.md              # (generated) Phase 0 hand-review output
  phase0-scores.csv             # (generated) Phase 0 scores, tabular
```
