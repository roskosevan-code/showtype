# Phase 0 — Rubric Sanity Check: Claude Code Task

This is the validation spike that gates the build. The goal is **not** to build anything — it is to find out, in an afternoon, whether the rubric in `docs/rubric.md` produces sane, useful axis scores before any pipeline exists. Run it, then judge the output by hand against the exit criteria at the bottom.

## How to run it

1. Make sure `docs/rubric.md` exists in the repo.
2. Review the gold-set list below and edit it: keep only shows **you know intimately**, and make sure the set still spreads across the axis space (see the stress-case groupings — don't let it collapse into 36 of your favorites).
3. Paste the task prompt below into Claude Code from the repo root.
4. When it finishes, open `docs/phase0-scores.md` and review against the exit criteria.

## The task prompt (paste into Claude Code)

> Read `docs/rubric.md` in full — the eight axis definitions, the scoring conventions, the calibration anchor table, and the worked examples.
>
> Then score every show in the list below on all eight axes. For each show and each axis, produce: an integer value 0–10, a one-to-two sentence justification that is concrete to that specific show (name the thing in the show that drives the score — no generic phrasing), and a confidence of `low`, `medium`, or `high`.
>
> Rules:
> - Reason from the axis definitions and anchors. Do **not** simply copy a similar anchor's numbers — score each show on its own merits, using the anchors only to calibrate what a given value means.
> - The axes are descriptive, not evaluative, and largely independent. Expect shows to score high on some axes and low on others. Do not let a show you regard as great score high across the board.
> - Do not invent facts about a show to sound confident. If you are unsure of a show or an axis reading is genuinely borderline, score conservatively and mark confidence `low`.
> - Pay attention to the known traps: propulsion is not speed or action; institutional setting is not the same as institutional sweep; a stylized show can still be high on verisimilitude; high register is only "corny" when paired with low verisimilitude.
>
> Output: write the results to `docs/phase0-scores.md` as a markdown file with (a) one section per show containing a small table of the eight axes with value / justification / confidence, and (b) a final "Flags" section listing any shows you were unsure about and any axes whose definitions felt ambiguous or hard to apply. Also emit a second file `docs/phase0-scores.csv` with columns: `show, axis, value, confidence, justification`.
>
> The shows to score:
> [paste your edited gold-set list here]

## Starter gold-set list

Edit freely. Grouped by what each cluster stress-tests — keep the spread when you trim.

**Sweep / scope maxed (systems storytelling):**
The Wire, Andor, Deadwood, Chernobyl, We Own This City, Babylon Berlin, The Shield

**Propulsion maxed, small scope/sweep:**
Breaking Bad, Better Call Saul, Happy Valley, Ozark

**Scope maxed:**
The Expanse, Foundation, Game of Thrones, ZeroZeroZero

**Interiority / authorial signature maxed:**
Mr. Robot, The Sopranos

**Restrained-realism spy & crime (low register, high verisimilitude):**
The Americans, Slow Horses, The Agency, Fauda, Line of Duty, Blue Lights

**Deliberate stress / negative cases:**
Silo (low propulsion / scope / sweep), Top Boy (small scope, the character-study mode), Severance (mystery-box withholding), Peaky Blinders (high register + low verisimilitude → the "corny" check), The West Wing (the "dated" / broadcast-density case), Person of Interest (procedural surface, low early density)

**High register, earned vs. unearned (the discriminator test):**
Deadwood (earned), Peaky Blinders (unearned), Rome

## What to look for when reviewing the output (the gate)

Judge the result against your own read of these shows:

- **Systematic axis errors.** Is one axis consistently off (e.g., conflating propulsion with action, or scoring institutional *setting* as institutional *sweep*)? That's a rubric-definition problem to fix, not a one-off.
- **Justification quality.** Are the justifications specific to each show, or generic and interchangeable? Hollow justifications mean the score isn't grounded in anything, even when the number happens to be right.
- **Confidence calibration.** Do the `high`-confidence scores actually look more accurate than the `low` ones? If confidence is noise, that's worth knowing before relying on it to route review.
- **Anchor consistency.** Where the gold set overlaps the calibration anchors, does the model roughly reproduce the anchor values? Large drift on the anchors themselves means the calibration isn't taking.
- **The teaching pairs.** Did Deadwood and Peaky Blinders both land high on register while splitting on verisimilitude? Did The Wire and Breaking Bad come out as near-opposites on propulsion vs. sweep? If the rubric can't reproduce these deliberate contrasts, it isn't discriminating yet.

**Exit:** if the scores are largely sane and the justifications are concrete, the rubric is good enough — proceed to Phase 1 and seed the `Axis` table from `docs/rubric.md`. If specific axes are consistently wrong or justifications are vague, revise the axis definitions and anchors in `docs/rubric.md` and re-run. Iterate here, where it costs an afternoon, not after the pipeline exists.
