#!/usr/bin/env python3
"""Generate docs/phase0-scores.md and docs/phase0-scores.csv from one source of truth.

Each show maps to 8 (value, confidence, justification) tuples in AXES order.
Anchor shows reproduce the rubric's calibration table by design.
"""
import csv
import os

AXES = [
    "Propulsion", "Scope", "Institutional Sweep", "Interiority",
    "Authorial Signature", "Verisimilitude", "Density", "Register",
]

H, M, L = "high", "medium", "low"

# show -> list of (value, confidence, justification), one per axis in AXES order.
SHOWS = {
"The Wire": [
 (3, H, "Deliberately withholds momentum; a full season assembles disconnected pieces before they cohere, so the pull is structural rather than scene-to-scene."),
 (9, H, "Spans every layer of a city at once — corners, docks, schools, City Hall, the newsroom."),
 (10, H, "The definitional case: the literal subject is how institutions perpetuate themselves regardless of the people inside; each season swaps in another one."),
 (1, H, "Almost purely sociological — it observes behavior and by design never explains a character's inner life."),
 (2, H, "Aggressively plain and anti-stylish; the craft is deliberately hidden."),
 (10, H, "Reads as reported journalism; the gold standard for lived-in texture."),
 (10, H, "Tracks nothing for the viewer — names, threads, and slang must be actively held."),
 (2, H, "Flat, naturalistic, restrained throughout."),
],
"Andor": [
 (7, H, "Tightly causal — the Aldhani heist and the Narkina 5 break each set the next move in motion with little idling."),
 (8, H, "Multiple planets, the Empire and the nascent Rebellion, several social strata from Ferrix labor to Coruscant elites."),
 (9, H, "The ISB, the prison, the Senate, and rebel cells are all rendered as functioning machines with their own logic — systems storytelling in a Star Wars shell."),
 (4, M, "Some access to Cassian and Luthen, but the mode is largely external and operational."),
 (6, H, "A strong, quietly commanding hand — composed framing, Mon Mothma's restraint, Luthen's monologue — without showiness."),
 (7, H, "Grounded, working-class textures and bureaucratic detail unusual for the franchise."),
 (7, H, "Many factions and names tracked without hand-holding across interlocking cells."),
 (4, M, "Mostly grounded and controlled, with occasional operatic swells (the funeral, the speech)."),
],
"Deadwood": [
 (4, H, "Slow and accretive; momentum comes from the camp coalescing over a season, not scene-to-scene cliffhangers."),
 (6, M, "One mining camp, but with a full social pyramid from the thoroughfare mud to the Hearst capital that reaches into it."),
 (9, H, "The birth of civic institutions — law, commerce, the press — out of lawlessness is the show's actual subject."),
 (5, M, "Some genuine interior (Bullock's rage, Al's calculation) amid a largely external ensemble."),
 (8, H, "Milch's blank-verse profanity and theatrical staging are instantly recognizable."),
 (8, H, "Researched and lived-in — the filth, the economics, the period cadence feel earned."),
 (8, H, "Dense vocabulary, large ensemble, and oblique scheming demand attention."),
 (8, H, "Shakespearean and operatic — but, paired with high verisimilitude, the earned high-register case."),
],
"Chernobyl": [
 (8, H, "A countdown engine: each scene exposes the next layer of the lie and tightens the consequence."),
 (6, M, "The plant, Pripyat, Moscow, and the mines — a wide social cross-section of the Soviet state."),
 (8, H, "The Soviet system of denial and self-protection is the true antagonist, traced from control room to Politburo."),
 (3, M, "Largely external; we watch institutional behavior more than inhabit any one mind."),
 (6, H, "A strong but quiet hand — the desaturated dread, the sound design, the procedural restraint."),
 (9, H, "Meticulously researched texture, from dosimetry to bureaucratic ritual."),
 (7, H, "Technical and political detail delivered with little hand-holding."),
 (3, H, "Controlled and restrained; horror conveyed through understatement."),
],
"We Own This City": [
 (5, M, "Moderate pull from the dual track of the GTTF's rise and the federal investigation closing in, but it favors anatomy over cliffhanger."),
 (5, M, "One city, but spanning street corners, the BPD, the DOJ, and the politics of the drug war."),
 (9, H, "Pure systems storytelling — the unit's corruption is framed as a product of the department and the war on drugs, not a few bad actors."),
 (2, M, "Simon's external, sociological mode; almost no inner access."),
 (4, M, "A restrained, journalistic hand — recognizably Simon, but craft kept out of the way."),
 (9, H, "Built from real reporting; the procedure and patois feel reported, not invented."),
 (8, M, "Time-jumping structure and a large unannotated cast demand active tracking."),
 (3, M, "Flat and naturalistic, anger held in check."),
],
"Babylon Berlin": [
 (7, M, "A conspiracy engine keeps the plot charging forward across interlocking intrigues."),
 (8, M, "Weimar Berlin in full social cross-section — police, underworld, communists, aristocrats, and rising fascists."),
 (6, M, "The era's machinery (police, Reichswehr, political factions) is a real subject, though conspiracy plotting often leads."),
 (5, M, "Gereon's shell-shock and morphine haze open a window inward amid a broad ensemble."),
 (8, M, "Lavish, expressionist spectacle — the 'Zu Asche' cabaret set piece is a signature flourish."),
 (8, M, "Obsessive period reconstruction of Weimar Berlin, richly textured."),
 (7, M, "Many factions, German political threads, and names to hold."),
 (7, M, "Heightened, maximalist, spectacle-forward."),
],
"The Shield": [
 (9, H, "Mackey's lies compound relentlessly; the opening murder of a cop sets a debt that detonates through every later season."),
 (4, M, "Confined to one LA district and the Barn; the canvas is a neighborhood."),
 (5, M, "Corruption inside the department is present, but the show is about Vic more than the institution as its own machine."),
 (3, M, "Largely external and propulsive; we infer rather than inhabit Vic's interior."),
 (4, M, "Urgent handheld immediacy, but not auteur-conspicuous."),
 (7, M, "Gritty, grounded cop-shop texture."),
 (6, M, "Serialized and rewarding attention without being punishing."),
 (5, M, "Mostly grounded, escalating to operatic intensity in the late seasons."),
],
"Breaking Bad": [
 (10, H, "Every decision detonates the next problem; the engine never idles."),
 (3, H, "Confined to one man and the people in his blast radius."),
 (1, H, "Not about a system — about an individual's transformation."),
 (8, H, "Lives largely inside Walt's self-justification and denial."),
 (6, H, "A strong, controlled visual style (cold opens, motifs) without foregrounding itself."),
 (7, H, "Grounded in plausible procedure, with some operatic heightening late."),
 (6, H, "Rewards attention and serialization but remains accessible."),
 (4, H, "Mostly grounded, with escalating operatic flourishes."),
],
"Better Call Saul": [
 (7, H, "A patient burn, but every Jimmy choice and Chuck slight tightens the road to Saul — consequence, not speed, drives it."),
 (4, H, "Albuquerque law and cartel orbits; a small, contained canvas."),
 (3, M, "The firm and the cartel are settings; the show is about a self, not a system."),
 (8, H, "Deeply interior — staged inside Jimmy's self-conception and Kim's complicity."),
 (8, H, "Among the most formally composed shows on TV — symmetrical framing, time-lapses, the black-and-white Gene frame."),
 (8, H, "Granular legal and grift procedure, meticulously textured."),
 (6, H, "Serialized and patient, rewarding attention without withholding cruelly."),
 (4, H, "Restrained and naturalistic, with tragic operatic notes."),
],
"Happy Valley": [
 (8, H, "Catherine's pursuit of Tommy Lee Royce is a tightening vise; dread escalates scene to scene."),
 (2, H, "One Yorkshire valley — the canvas is deliberately small."),
 (4, M, "Policing is the setting, but the real subject is a family's trauma, not the institution."),
 (7, H, "Stays close to Catherine's grief and grit; her interior is the spine."),
 (4, M, "Plain, naturalistic British social-realist craft."),
 (9, H, "Reads as utterly lived-in — the texture of small-town policing and family is exact."),
 (6, M, "Serialized and attentive but accessible."),
 (2, H, "Restrained, understated, deadpan in its grimness."),
],
"Ozark": [
 (8, H, "Each episode ratchets the Byrdes' peril; the plot seldom rests."),
 (4, M, "The Missouri Ozarks plus cartel and local crime — moderate, contained canvas."),
 (3, M, "Cartel and FBI are forces, not the subject; this is a family under pressure, not systems storytelling."),
 (4, M, "Some access to Marty and Wendy, but plotting outweighs interiority."),
 (6, H, "A signature desaturated blue-grey palette makes it recognizable on sight."),
 (6, M, "Grounded laundering procedure, though plotting can strain plausibility."),
 (5, M, "Moderate demand; followable while serialized."),
 (5, M, "Mostly restrained, escalating to operatic family melodrama."),
],
"The Expanse": [
 (9, H, "Crises cascade across factions; each political move forces the next."),
 (10, H, "Solar-system-wide, with three powers (Earth, Mars, the Belt) — a maximal canvas."),
 (8, H, "The machinery of UN, Martian, and Belter politics is rendered as functioning systems."),
 (4, M, "Largely external and plot-driven; interiority is secondary to incident."),
 (4, M, "Competent and clean but not strongly auteur-stamped."),
 (8, H, "Rigorous physics and a believable Belter culture and creole."),
 (8, H, "Many factions, names, and political threads to track."),
 (4, M, "Mostly grounded, with operatic stakes."),
],
"Foundation": [
 (4, M, "Century-spanning time jumps and mystery-box withholding keep it from compounding scene to scene."),
 (10, M, "Galaxy-spanning across millennia — scope is maximal."),
 (7, M, "The genetic Cleon dynasty and psychohistory frame empire as a self-perpetuating system."),
 (4, L, "Some access to Gaal and Demerzel, but spectacle dominates over interior."),
 (6, M, "Lavish, distinctive production design and a grand directorial hand."),
 (4, M, "Mythologized space opera; texture is grand rather than reported."),
 (6, M, "Multiple timelines and names demand tracking, offset by spectacle."),
 (7, M, "Operatic and grand in register."),
],
"Game of Thrones": [
 (8, H, "Early seasons compound ruthlessly — Ned's fall cascades into war — though late seasons lose the causal grip."),
 (10, H, "Continents plus every social stratum, from Wall to Essos — a maximal canvas."),
 (6, M, "Great houses, faiths, and the Watch are vivid institutions, but dynastic intrigue, not systems analysis, is the mode."),
 (4, M, "Mostly external ensemble, with pockets of interior (Tyrion, Jaime)."),
 (6, H, "High craft and recognizable scale, but not eccentric auteurism."),
 (6, M, "Grounded medieval texture early; fantasy elements grow."),
 (8, H, "Vast cast, houses, and shifting allegiances to track without much help."),
 (7, H, "Operatic and maximalist."),
],
"ZeroZeroZero": [
 (7, H, "The cocaine shipment functions as a relentless relay baton, propelling across continents."),
 (9, H, "Three continents and the full supply chain — a near-maximal geographic canvas."),
 (7, M, "The global narco supply chain is rendered as a system, from 'Ndrangheta to brokers to cartels."),
 (3, M, "Cold and external; almost no inner access."),
 (7, M, "A severe, formally controlled style with Mogwai's score giving a strong sonic signature."),
 (8, H, "Tradecraft, logistics, and milieu feel meticulously real."),
 (7, M, "Parallel strands across languages and names demand work."),
 (4, M, "Restrained and grim, with occasional operatic dread."),
],
"Mr. Robot": [
 (8, H, "Elliot's spiraling scheme drives relentlessly; reveals reframe and re-propel the story."),
 (6, M, "New York and fsociety widening to global finance — moderate-to-large social canvas."),
 (7, M, "E Corp and the surveillance-finance complex operate as a real systemic subject."),
 (10, H, "The entire show is staged inside one unreliable narrator's mind, direct-address included."),
 (10, H, "Off-center framing, direct address, and formal sleight-of-hand make it recognizable in a single shot."),
 (8, H, "Meticulous, accurate hacking and infosec texture despite heavy stylization."),
 (8, H, "Withholds and misdirects; demands active reconstruction of what is real."),
 (6, M, "Heightened and stylized, though anchored by naturalistic performance."),
],
"The Sopranos": [
 (6, H, "Steady forward pressure from Tony's double life, though it indulges digression and dream by design."),
 (5, M, "North Jersey mob and family — a mid-size social canvas."),
 (5, M, "The Family operates as an institution, but the show is finally about a psyche, not a system."),
 (9, H, "The therapy frame makes Tony's interior — guilt, panic, denial — the literal text."),
 (6, H, "A strong, controlled hand (the dream sequences, the cut-to-black grammar) without constant flash."),
 (8, H, "Richly observed suburban-mob texture, lived-in and specific."),
 (7, H, "Allusive and unhurried, trusting the viewer to sit with ambiguity."),
 (4, M, "Mostly naturalistic, with operatic and surreal excursions."),
],
"The Americans": [
 (8, H, "Each mission and each marital lie compounds; the wig-and-cover work always escalates the next crisis."),
 (6, M, "Cold War Washington with Moscow ties — moderate social and geopolitical canvas."),
 (6, M, "The KGB rezidentura and FBI counterintelligence are real systems, though the marriage is the heart."),
 (7, H, "Deeply interior — the cost to Philip and Elizabeth's selves is the real drama."),
 (4, M, "Controlled and unshowy; period naturalism over visible authorship."),
 (9, H, "Tradecraft and period texture feel reported and exact."),
 (7, H, "Quiet, patient, and trusting; little exposition."),
 (3, H, "Restrained and controlled, tension held under the surface."),
],
"Slow Horses": [
 (8, H, "Tight, propulsive plotting — each blunder by Slough House forces a scramble that tightens the next."),
 (5, M, "London and the Service — a moderate, contained canvas."),
 (6, M, "MI5's bureaucratic pecking order and the dumping ground of Slough House are a real subject of satire."),
 (4, M, "Largely external; Lamb and Cartwright are read from behavior, not interior."),
 (5, M, "Polished and witty but not strongly auteur-stamped."),
 (7, M, "Grounded, unglamorous spookery with credible institutional grime."),
 (6, M, "Brisk and serialized, rewarding attention without punishing."),
 (4, M, "Mostly dry and restrained, with comic and occasional operatic spikes."),
],
"The Agency": [
 (6, L, "A deliberate slow-burn spy register; tension accrues through tradecraft rather than incident."),
 (5, L, "A CIA London station with global operations — moderate canvas."),
 (7, L, "Following Le Bureau, the station's tradecraft and bureaucracy are much the subject."),
 (5, L, "Martian's compromised romance opens some interior, but the read is uncertain."),
 (4, L, "Glossy prestige restraint; no strong auteur signature evident yet."),
 (7, L, "Tradecraft-forward and grounded, though the show is too new to be sure."),
 (6, L, "Tradecraft detail and competing threads demand moderate attention."),
 (3, L, "Restrained and controlled in tone."),
],
"Fauda": [
 (8, M, "Kinetic and cliffhanger-driven; raids and reprisals escalate in a tight loop."),
 (5, M, "Israel and the West Bank — two societies, a moderate social canvas."),
 (4, M, "The undercover unit is a setting more than a dissected institution; action and character lead."),
 (5, M, "Notably humanizes both sides, giving real interior to antagonists as well as Doron."),
 (4, M, "Urgent, handheld immediacy without conspicuous authorship."),
 (8, M, "Gritty, bilingual, both-sides texture that feels reported."),
 (6, M, "Multiple factions and names, moderately demanding."),
 (4, M, "Mostly grounded, with melodramatic surges."),
],
"Line of Duty": [
 (8, H, "The marathon interrogations and twist reveals make each episode pull hard into the next."),
 (3, M, "One anti-corruption unit and its cases — a small canvas."),
 (7, M, "Institutional corruption is the literal subject: AC-12 versus 'bent coppers' and OCG infiltration of the force."),
 (3, M, "Procedural and external; little inner life."),
 (4, M, "The interrogation set-piece is a signature device, but the surface is TV-naturalist."),
 (6, M, "Procedural authenticity (protocol, acronyms) is high, though late-series twists strain it."),
 (7, M, "Dense with acronyms (CHIS, UCO, OCG) and protocol, with no hand-holding."),
 (4, M, "Mostly restrained, spiking to heightened confrontation."),
],
"Blue Lights": [
 (6, M, "Steady tension from rookie mistakes and Belfast's live threats, building rather than idling."),
 (3, M, "One city's policing — a small, contained canvas."),
 (5, M, "The PSNI and post-Troubles community and paramilitary dynamics are present, but the focus is the rookies."),
 (4, M, "Rookie POV gives some interior access amid an ensemble."),
 (3, M, "Plain, naturalistic social-realist craft."),
 (8, M, "Specific, researched Belfast policing texture that feels lived-in."),
 (5, M, "Moderate demand; followable."),
 (3, M, "Restrained and naturalistic."),
],
"Silo": [
 (2, H, "Doles out crumbs instead of escalating; the mystery is rationed rather than compounded."),
 (3, M, "Confined to a single underground silo — a small physical canvas."),
 (4, M, "The silo's governance and secrecy hint at a system, but it stays backdrop more than dissected machine."),
 (4, M, "Some access to Juliette, but the mode is largely external."),
 (4, M, "Competent, muted dystopian style without strong authorial stamp."),
 (5, M, "Functional world-building; texture is adequate, not richly reported."),
 (5, M, "Moderate — a mystery to track but heavily sign-posted."),
 (3, M, "Restrained and grim in register."),
],
"Top Boy": [
 (5, M, "More slice-of-life than cliffhanger; tension simmers in the character-study mode rather than charging forward."),
 (3, M, "Centered on one London estate — a deliberately small canvas."),
 (4, M, "The drug economy and gentrification give systemic texture, but the focus stays on a few lives."),
 (5, M, "Real interior for Dushane and Sully under the street surface."),
 (5, M, "Atmospheric and grounded, with a restrained but distinct mood."),
 (8, M, "Lived-in London estate texture, slang and economics exact."),
 (6, M, "Slang and names to hold, moderately demanding."),
 (3, M, "Restrained and naturalistic."),
],
"Severance": [
 (5, M, "More withholding than propulsive — a mystery-box that rations revelation, save for the finale's surge."),
 (3, M, "Lumon's office floor and a small town — a confined canvas."),
 (6, M, "Lumon as cultic corporate institution is much the subject — the machine that owns its workers."),
 (7, M, "The innie/outie split makes divided consciousness and selfhood the literal premise."),
 (9, H, "Stiller's symmetrical, retro-modern design is unmistakable in a single frame."),
 (3, M, "Deliberately unreal and allegorical; not aiming for reported texture."),
 (7, M, "Withholds exposition; the viewer must assemble the mystery."),
 (6, M, "Stylized and heightened in design, yet deadpan in tone — a register that sits oddly between poles."),
],
"Peaky Blinders": [
 (8, H, "Kinetic and momentum-forward, always charging to the next confrontation."),
 (7, M, "Expands from a Birmingham gang to London, Westminster, and international politics."),
 (5, M, "The Shelby enterprise becomes quasi-institutional, but the system is not the real subject."),
 (4, M, "Some access to Tommy, but the mode is external mythologizing."),
 (7, H, "Highly stylized — slow motion, anachronistic music, posed swagger."),
 (3, H, "Mythologized and anachronistic; glamour over lived-in texture."),
 (5, M, "Moderate; the plotting is followable without much work."),
 (9, H, "Operatic and maximalist — and, combined with low verisimilitude, the 'corny' reading."),
],
"The West Wing": [
 (5, M, "Walk-and-talk urgency gives drive, but episodes are largely self-contained crises that reset."),
 (5, M, "The White House and national politics — a moderate institutional canvas."),
 (6, M, "The workings of the executive branch are a genuine subject, albeit idealized."),
 (3, M, "External and dialogue-driven; little interior staging."),
 (6, H, "Sorkin's cadence and rhythm are an instantly recognizable authorial voice."),
 (5, M, "Aspirational and idealized rather than grittily reported — credible but burnished."),
 (5, M, "Fast policy talk, but broadcast design recaps and self-explains — the dated, lower-density case."),
 (4, M, "Earnest and somewhat heightened in idealism, but naturalistic in delivery."),
],
"Person of Interest": [
 (6, M, "A procedural case-of-the-week surface early that becomes intensely serialized and propulsive once the AI war takes over."),
 (6, M, "New York early, widening to a global surveillance conflict."),
 (6, M, "The Machine and Samaritan turn the surveillance state itself into the show's systemic subject."),
 (3, M, "External and plot-driven; little interiority."),
 (4, M, "Slick network-procedural craft early, without strong auteur signature."),
 (5, M, "Tech-thriller plausibility with network gloss — moderate texture."),
 (5, M, "Low early by design (self-contained numbers), rising to high serialized density later."),
 (5, M, "Mostly grounded, escalating toward operatic sci-fi stakes."),
],
"Rome": [
 (7, M, "Vorenus and Pullo thread a strong narrative drive through the historical machinery."),
 (8, M, "Republic-to-empire Rome plus Egypt, spanning every social stratum from slave to Senate."),
 (7, M, "The Roman political machine — Senate, patronage, religion, the legions — is a real subject."),
 (3, M, "Largely external; we read the players from behavior, not interior."),
 (6, M, "Lavish HBO craft with a strong but not eccentric hand."),
 (8, M, "Researched grime — graffiti, ritual, class — gives earned ancient texture."),
 (7, M, "Politics, factions, and names demand active tracking."),
 (8, M, "Operatic and grand, and — paired with high verisimilitude — earned rather than corny."),
],
}

FLAGS_SHOWS = """\
- **The Agency** — scored throughout at `low` confidence: it is recent and not yet canonical, and several readings (interiority, register) are provisional. Treat its row as a placeholder pending a closer watch.
- **Foundation** — confident on Scope (10) but unsure on Propulsion and Verisimilitude; the time-jump structure makes "does each scene create the next" genuinely hard to read.
- **Babylon Berlin / Fauda / Blue Lights / Top Boy** — held at `medium`: well-textured reads, but I am less intimately versed than on the anchor set, so the borderline axes (Sweep especially) are conservative.
- **Person of Interest** and **The West Wing** — flagged in the task as the early-density / broadcast-density cases; their Density and Propulsion scores reflect a whole-run average, which masks a strong early-vs-late split worth noting in review."""

FLAGS_AXES = """\
- **Institutional Sweep vs. institutional setting** — the hardest line to hold consistently. The Shield, Line of Duty, Happy Valley, and Blue Lights are all set in police forces but differ sharply in whether the institution is the *subject*. Scores tried to honor that distinction (We Own This City 9 vs. Happy Valley 4), but it is the axis most prone to drift.
- **Register for stylized-but-deadpan shows** — Severance exposes a gap: its design is maximalist (high) while its tone is flat and deadpan (low). The single 0–10 axis collapses two things; a note in the rubric on how to weigh visual maximalism against tonal restraint would help.
- **Density across a run** — for shows that change mode (Person of Interest, Game of Thrones), a single number averages over seasons. The rubric may want guidance on whether to score the pilot's contract or the series' peak.
- **Propulsion for mystery-box shows** — Silo and Severance both "withhold," but withholding can still feel propulsive. The definition's "incident without escalation" helped, but distinguishing rationed-mystery from genuine escalation stayed judgment-heavy."""


def fmt_table(rows):
    out = ["| Axis | Value | Confidence | Justification |",
           "|------|:-----:|:----------:|---------------|"]
    for axis, (val, conf, just) in zip(AXES, rows):
        out.append(f"| {axis} | {val} | {conf} | {just} |")
    return "\n".join(out)


def write_md(path):
    parts = []
    parts.append("# Phase 0 — Rubric Sanity-Check Scores\n")
    parts.append(
        "Hand-scored output of the Phase 0 spike: every show in the starter gold set "
        "rated on the eight axes of `docs/rubric.md`, with a concrete justification and "
        "a confidence per cell. Scored in a single pass for cross-show consistency; "
        "anchor shows reproduce the rubric's calibration table by design.\n")
    parts.append(
        "> **Review note:** this is the gate, not the product. Judge it against your own "
        "read of these shows per the exit criteria in "
        "`docs/phase-0-claude-code-task.md` — focus on the shows you know intimately.\n")
    for show, rows in SHOWS.items():
        parts.append(f"## {show}\n")
        parts.append(fmt_table(rows) + "\n")
    parts.append("## Flags\n")
    parts.append("### Shows I was unsure about\n")
    parts.append(FLAGS_SHOWS + "\n")
    parts.append("### Axis definitions that felt ambiguous or hard to apply\n")
    parts.append(FLAGS_AXES + "\n")
    parts.append("### Teaching-pair check\n")
    parts.append(
        "- **The Wire (Prop 3 / Sweep 10) vs. Breaking Bad (Prop 10 / Sweep 1)** — came "
        "out as near-opposites, as intended.\n"
        "- **Deadwood (Veris 8, Reg 8) vs. Peaky Blinders (Veris 3, Reg 9)** — both high "
        "register; verisimilitude splits them, reproducing the earned/unearned contrast. "
        "Rome (Veris 8, Reg 8) lands with Deadwood on the earned side.\n"
        "- **Mr. Robot (Auth 10, Veris 8)** — heavy stylization and high authenticity "
        "coexist, confirming those axes read as independent.\n")
    with open(path, "w") as f:
        f.write("\n".join(parts))


def write_csv(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["show", "axis", "value", "confidence", "justification"])
        for show, rows in SHOWS.items():
            for axis, (val, conf, just) in zip(AXES, rows):
                w.writerow([show, axis, val, conf, just])


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    # default: ../docs relative to this script (scripts/ -> repo root -> docs/)
    docs = os.path.normpath(os.path.join(here, "..", "docs"))
    # allow override of output dir via arg
    import sys
    outdir = sys.argv[1] if len(sys.argv) > 1 else docs
    os.makedirs(outdir, exist_ok=True)
    write_md(os.path.join(outdir, "phase0-scores.md"))
    write_csv(os.path.join(outdir, "phase0-scores.csv"))
    n_shows = len(SHOWS)
    print(f"wrote {n_shows} shows x {len(AXES)} axes = {n_shows*len(AXES)} cells")
    print(f"  {os.path.join(outdir, 'phase0-scores.md')}")
    print(f"  {os.path.join(outdir, 'phase0-scores.csv')}")
