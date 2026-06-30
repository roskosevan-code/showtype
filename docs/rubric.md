# The Taste Index — Scoring Rubric (v1)

This document defines the eight axes used to characterize a TV show, how to score each one, and a set of calibration anchors that keep scoring consistent across the catalog. It has two uses: it is the reference a scorer (human or model) reads before scoring, and it is seeded verbatim into the `Axis` table in Phase 1. Revise this document — not code — when an axis is mis-reading.

## Scoring conventions

- **Scale:** each axis is an integer **0–10**. The axes are *descriptive, not evaluative* — a high or low score is not "good" or "bad," it just locates the show. Quality is tracked separately.
- **Justification:** one to two sentences per axis, **concrete to the specific show** (name the thing in the show that drives the score). "High momentum" is a non-answer; "each episode's cliffhanger forces the next, and no subplot is ever left idling" is a justification.
- **Confidence:** `low` / `medium` / `high`, reflecting how well-known the show is and how clear-cut the reading is. A famous show with an obvious reading is `high`; an obscure show, or a genuinely borderline axis, is `low`. **Do not invent facts about a show to raise confidence** — if unsure, score conservatively and mark `low`.
- **Independence:** score each axis on its own. The axes are designed to be largely independent, and the interesting shows score high on some and low on others. Resist the pull to make a show you admire score high on everything.

## The eight axes

### 1. Propulsion
Forward momentum — the sense that each scene creates the conditions for the next, that the story is always pushing into what comes next.
- **This is not speed or action.** A slow, talky show can be intensely propulsive (drive comes from consequence and escalation); a fast, eventful show can lack it (incidents that don't compound).
- **Low (0–2):** circles, withholds, idles; incident without escalation.
- **High (8–10):** "just one more episode" feels involuntary; every choice tightens the situation.
- Anchors: *Breaking Bad* 10 (each choice detonates the next problem); *The Wire* 3 (deliberately refuses cheap momentum); *Silo* 2 (doles out crumbs instead of escalating).

### 2. Scope
The size of the canvas — how much world there is. Can be **geographic** (how many places), **temporal** (how much time), or **social** (how many strata/factions). Score the largest of the three.
- **Low (0–2):** one place, one small group, a confined timeframe.
- **High (8–10):** continents, centuries, or every layer of a society at once.
- Anchors: *The Expanse* 10 (solar-system-wide, three powers); *Happy Valley* 2 (one Yorkshire valley); *Game of Thrones* 10 (continents + every social stratum).

### 3. Institutional Sweep
The degree to which a **system or institution is the show's real subject** — tracing how the machine works and how people are shaped, used, and ground down by it ("systems storytelling").
- **Distinguish from merely having an institutional setting.** A show can be set in a police force without being *about* the institution. The test: is the institution itself effectively a character with its own logic?
- **Low (0–2):** institutions are backdrop or absent.
- **High (8–10):** the institution's self-perpetuating logic is the point.
- Anchors: *The Wire* 10 (the definitional case — each season another institution); *Andor* 9 (ISB, prison, Senate, cells all as functioning machines); *Breaking Bad* 1 (about one man, not a system).

### 4. Interiority (Depth)
How far the show goes *inside* a consciousness versus observing behavior from the outside. The vertical complement to scope's horizontal.
- **Low (0–2):** purely external/sociological; the show watches what people do and never explains a soul.
- **High (8–10):** the show is substantially staged inside a mind.
- Anchors: *Mr. Robot* 10 (the entire show is inside one unreliable narrator); *The Wire* 1 (almost no inner access by design); *The Sopranos* 9 (the therapy frame makes Tony's interior the text).

### 5. Authorial Signature (Formal Ambition)
Invisible craft versus visible auteur stylization — would you recognize the show blind? This measures the **strength and distinctiveness** of the authorial presence, which can be loud *or* quiet.
- **Low (0–2):** deliberately plain; technique effaced; wants you to forget the camera.
- **High (8–10):** a strong, recognizable hand — whether showy (direct address, structural tricks) or quietly commanding.
- **Distinguish from Register (axis 8):** this axis is *visual and formal* boldness; tonal/emotional pitch is register. A show can be visually maximalist yet tonally deadpan (*Severance*: high here, low there).
- Anchors: *Mr. Robot* 10 (off-center framing, direct address, formal sleight-of-hand); *The Wire* 2 (anti-stylish on purpose); *Chernobyl* 6 / *Andor* 6 (a strong hand, quietly).

### 6. Verisimilitude (Texture)
How authentic, granular, and lived-in the world feels — independent of how big it is and independent of how stylized it is.
- **Independent of authorial signature:** a heavily stylized show can be meticulously authentic (*Mr. Robot* is both).
- **Low (0–2):** mythologized, anachronistic, glamorized, unearned.
- **High (8–10):** feels reported, researched, like the writers did the homework.
- Anchors: *ZeroZeroZero* 8 / *The Americans* 9 (tradecraft and texture feel real); *The Wire* 10 (the gold standard); *Peaky Blinders* 3 (mythologized and anachronistic).

### 7. Density (Demand)
How much the show asks of the viewer per minute — its willingness to withhold exposition and trust you to keep up.
- **Low (0–2):** recaps, exposition, self-contained episodes; hand-holding (typical of broadcast/procedural design).
- **High (8–10):** no hand-holding; threads and names you must actively track.
- Anchors: *The Wire* 10 (tracks nothing for you); *The Expanse* 8 (many factions/names); broadcast procedurals 1–2 (by design).

### 8. Register (Tonal Control)
Where the show sits on the **restrained ↔ operatic** spectrum of *tonal and emotional pitch* — how heightened the performances, dialogue, music, and dramatic stakes are played. Descriptive, not a quality judgment.
- **This is tonal pitch, not visual boldness.** Stylized design, bold framing, and formal tricks belong to **Authorial Signature** (axis 5), not here. A show can have a loud, unmistakable authorial hand and still be tonally restrained — score the emotional key, not the production design. *Severance* is the test case: its symmetrical, retro-modern design is maximalist (high Authorial Signature), yet its performances and tone are deliberately muted and deadpan (low register, ~3–4).
- **Low (0–2):** restrained, naturalistic, understated, deadpan; emotions played cool and stakes underplayed.
- **High (8–10):** operatic, heightened, maximalist, melodramatic; emotions and stakes pitched loud.
- **Note on "corny":** a high-register show is not automatically corny. "Corny" typically means **high register *combined with* low verisimilitude** — heightened style that hasn't been earned. High register with high verisimilitude can be superb (*Deadwood*). Whether the register is executed with command is a quality matter handled outside this number.
- Anchors: *Chernobyl* 3 / *The Americans* 3 (restrained, controlled); *Deadwood* 8 (Shakespearean and operatic, but earned); *Peaky Blinders* 9 (operatic swagger).

## Calibration anchor table

Reference values for well-established shows, used as few-shot calibration. A scorer should be able to roughly reproduce these from the definitions; large divergence signals a rubric or reasoning problem. Columns: **Prop**ulsion, **Scope**, **Sweep** (institutional), **Inter**iority, **Auth**orial signature, **Veris**imilitude, **Dens**ity, **Reg**ister.

| Show | Prop | Scope | Sweep | Inter | Auth | Veris | Dens | Reg |
|---|---|---|---|---|---|---|---|---|
| The Wire | 3 | 9 | 10 | 1 | 2 | 10 | 10 | 2 |
| Breaking Bad | 10 | 3 | 1 | 8 | 6 | 7 | 6 | 4 |
| The Sopranos | 6 | 5 | 5 | 9 | 6 | 8 | 7 | 4 |
| The Expanse | 9 | 10 | 8 | 4 | 4 | 8 | 8 | 4 |
| Mr. Robot | 8 | 6 | 7 | 10 | 10 | 8 | 8 | 6 |
| Silo | 2 | 3 | 4 | 4 | 4 | 5 | 5 | 3 |
| Peaky Blinders | 8 | 7 | 5 | 4 | 7 | 3 | 5 | 9 |
| Happy Valley | 8 | 2 | 4 | 7 | 4 | 9 | 6 | 2 |
| Chernobyl | 8 | 6 | 8 | 3 | 6 | 9 | 7 | 3 |
| The Americans | 8 | 6 | 6 | 7 | 4 | 9 | 7 | 3 |
| Andor | 7 | 8 | 9 | 4 | 6 | 7 | 7 | 4 |
| ZeroZeroZero | 7 | 9 | 7 | 3 | 7 | 8 | 7 | 4 |
| Deadwood | 4 | 6 | 9 | 5 | 8 | 8 | 8 | 8 |
| Slow Horses | 8 | 5 | 6 | 4 | 5 | 7 | 6 | 4 |

### Teaching pairs (why the anchors are chosen)
- **The Wire vs. Breaking Bad** — propulsion is independent of scope and sweep. One is low-propulsion but scope/sweep-maximal; the other is the inverse.
- **Deadwood vs. Peaky Blinders** — both score high on register (operatic). Verisimilitude is the discriminator: Deadwood's world is researched and lived-in (earned), Peaky's is mythologized (the "corny" reading).
- **Mr. Robot** — authorial signature 10 *and* verisimilitude 8: heavy stylization and meticulous authenticity coexist, proving those two axes are independent.
- **Silo** — the low-propulsion / low-scope / low-sweep profile worth recognizing on sight.

## Worked justification examples

These model the expected output — concrete, specific, one to two sentences.

**The Wire**
- *Propulsion 3:* Deliberately withholds momentum; a full season assembles disconnected pieces before they cohere, so the pull is structural rather than scene-to-scene.
- *Scope 9:* Spans every layer of a city — corners, docks, schools, City Hall, the press.
- *Institutional Sweep 10:* The literal subject is how institutions perpetuate themselves regardless of the people inside them; each season swaps in another one.
- *Interiority 1:* Almost purely sociological — it observes behavior and never explains a character's inner life.
- *Authorial Signature 2:* Aggressively plain and anti-stylish; the craft is hidden on purpose.
- *Verisimilitude 10:* Reads as reported journalism; the texture of the work is the gold standard.
- *Density 10:* Tracks nothing for the viewer — names, threads, and slang must be actively held.
- *Register 2:* Flat, naturalistic, restrained.

**Breaking Bad**
- *Propulsion 10:* Every decision detonates the next problem; the engine never idles.
- *Scope 3:* Confined to one man and the people in his blast radius.
- *Institutional Sweep 1:* Not about a system — about an individual's transformation.
- *Interiority 8:* Lives largely inside Walt's self-justification and denial.
- *Authorial Signature 6:* A strong, controlled visual style (cold opens, motifs) without foregrounding itself.
- *Verisimilitude 7:* Grounded in plausible procedure, with some operatic heightening late.
- *Density 6:* Rewards attention and serialization but remains accessible.
- *Register 4:* Mostly grounded, with escalating operatic flourishes.

**Peaky Blinders**
- *Propulsion 8:* Kinetic and momentum-forward, always charging to the next confrontation.
- *Scope 7:* Expands from a Birmingham gang to London, Westminster, and international politics.
- *Institutional Sweep 5:* The Shelby enterprise becomes quasi-institutional, but the system is not the real subject.
- *Interiority 4:* Some access to Tommy, but the mode is external mythologizing.
- *Authorial Signature 7:* Highly stylized — slow motion, anachronistic music, posed swagger.
- *Verisimilitude 3:* Mythologized and anachronistic; glamour over lived-in texture.
- *Density 5:* Moderate; the plotting is followable without much work.
- *Register 9:* Operatic and maximalist — and combined with the low verisimilitude, this is the "corny" reading.
