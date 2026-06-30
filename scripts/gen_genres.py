#!/usr/bin/env python3
"""Author docs/genres.csv: one primary genre per catalog show.

Genre is categorical metadata (not a structural rubric axis), curated by hand
from a tight controlled vocabulary. Authored as genre -> [shows] buckets for
easy review; validated for exact, complete coverage of docs/catalog-scores.csv;
emitted as a flat show,genre CSV.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "docs" / "catalog-scores.csv"
OUT = REPO / "docs" / "genres.csv"

GENRES: dict[str, list[str]] = {
    "Crime": [
        "Animal Kingdom", "Babylon Berlin", "Banshee", "Better Call Saul", "Bloodline",
        "Blue Lights", "Boardwalk Empire", "Bosch", "Breaking Bad", "Collateral",
        "Dexter", "Fargo", "Forbrydelsen (The Killing)", "Giri/Haji", "Gomorrah",
        "Happy Valley", "Hill Street Blues", "Homicide: Life on the Street", "Justified",
        "Line of Duty", "Lupin", "Luther", "Marcella", "Mindhunter", "Money Heist",
        "NYPD Blue", "Narcos", "Narcos: Mexico", "Oz", "Ozark", "Peaky Blinders",
        "Perry Mason", "Power", "Ray Donovan", "Reacher", "Sneaky Pete", "Snowfall",
        "Sons of Anarchy", "Spiral (Engrenages)", "Suburra", "The Bridge (Bron/Broen)",
        "The Fall", "The Killing", "The Night Of", "The Responder", "The Shield",
        "The Sopranos", "The Tunnel", "The Wire", "Tokyo Vice", "Top Boy",
        "True Detective", "Unforgotten", "Wallander", "We Own This City", "Your Honor",
        "ZeroZeroZero",
    ],
    "Thriller": [
        "Alias", "Berlin Station", "Bodyguard", "Damages", "Deutschland 83", "Fauda",
        "Homeland", "Killing Eve", "Mr. Robot", "Patriot", "Slow Horses", "Squid Game",
        "Tehran", "The Agency", "The Americans", "The Glory", "The Night Manager",
        "Tom Clancy's Jack Ryan",
    ],
    "Drama": [
        "Beef", "Big Little Lies", "Billions", "Chernobyl", "Crash Landing on You", "ER",
        "Friday Night Lights", "Halt and Catch Fire", "House", "Industry", "Mad Men",
        "My Brilliant Friend", "Normal People", "Olive Kitteridge",
        "Orange Is the New Black", "Patrick Melrose", "Rectify", "Reply 1988",
        "Show Me a Hero", "Six Feet Under", "St. Elsewhere", "Succession", "The Bear",
        "The Crown", "The Deuce", "The Good Fight", "The Good Wife", "The Knick",
        "The Leftovers", "The Newsroom", "The Young Pope", "This Is Us", "Treme",
        "Vinyl", "Years and Years",
    ],
    "Political": ["Borgen", "House of Cards", "The West Wing"],
    "Sci-Fi": [
        "1899", "3 Body Problem", "Altered Carbon", "Andor", "Battlestar Galactica",
        "Black Mirror", "Counterpart", "Dark", "Devs", "Doctor Who", "Fallout",
        "Farscape", "Firefly", "Foundation", "Fringe", "Loki", "Lost", "Lost in Space",
        "Maniac", "Person of Interest", "Raised by Wolves", "Sense8", "Severance",
        "Silo", "Snowpiercer", "Star Trek: Deep Space Nine",
        "Star Trek: The Next Generation", "Stargate SG-1", "Station Eleven",
        "Stranger Things", "Tales from the Loop", "The Boys", "The Expanse",
        "The Handmaid's Tale", "The Last of Us", "The Mandalorian", "The OA",
        "The Twilight Zone", "The Umbrella Academy", "The X-Files", "WandaVision",
        "Watchmen", "Westworld",
    ],
    "Fantasy": [
        "American Gods", "Angel", "Buffy the Vampire Slayer", "Game of Thrones",
        "His Dark Materials", "House of the Dragon", "Outlander", "The Wheel of Time",
        "The Witcher", "Wednesday",
    ],
    "Comedy": [
        "30 Rock", "Abbott Elementary", "Arrested Development", "Atlanta", "Barry",
        "Better Things", "BoJack Horseman", "Brooklyn Nine-Nine", "Call My Agent",
        "Cheers", "Community", "Curb Your Enthusiasm", "Eastbound & Down", "Fleabag",
        "Frasier", "Gilmore Girls", "Girls", "Hacks",
        "It's Always Sunny in Philadelphia", "Master of None", "PEN15",
        "Parks and Recreation", "Reservation Dogs", "Russian Doll", "Schitt's Creek",
        "Search Party", "Seinfeld", "Sex Education", "Silicon Valley", "Ted Lasso",
        "The End of the Fxxking World", "The Good Place", "The Larry Sanders Show",
        "The Marvelous Mrs. Maisel", "The Office", "The Office (UK)", "Veep",
        "What We Do in the Shadows",
    ],
    "Horror": [
        "Hannibal", "Hellbound", "Kingdom", "Lovecraft Country", "Midnight Mass",
        "Penny Dreadful", "The Haunting of Hill House", "The Returned (Les Revenants)",
        "The Terror",
    ],
    "War": ["Band of Brothers", "Generation Kill"],
    "Western": ["Deadwood", "Yellowstone"],
    "Historical": [
        "Black Sails", "Pachinko", "Rome", "Shogun", "The Plot Against America", "Vikings",
    ],
    "Mystery": [
        "Broadchurch", "Mare of Easttown", "Sharp Objects", "Sherlock", "The Sinner",
        "Top of the Lake", "Twin Peaks", "Veronica Mars",
    ],
}


# Additional genres beyond the primary, for genuinely cross-genre shows. The
# primary (from GENRES above) stays rank 0; these are rank 1+. Kept deliberately
# sparse and cross-tonal (we don't append "Drama" to everything, which would make
# the Drama filter meaningless).
SECONDARY: dict[str, list[str]] = {
    # comedy <-> other (dark comedies / dramedies that genuinely play funny)
    "Barry": ["Crime"], "Fargo": ["Comedy"], "Killing Eve": ["Comedy"],
    "Slow Horses": ["Comedy"], "Patriot": ["Comedy"], "Beef": ["Comedy"],
    "The Bear": ["Comedy"], "Orange Is the New Black": ["Comedy"],
    "Search Party": ["Mystery"], "Maniac": ["Comedy"], "Veronica Mars": ["Crime"],
    "Russian Doll": ["Sci-Fi"], "What We Do in the Shadows": ["Fantasy"],
    "The Good Place": ["Fantasy"], "Wednesday": ["Mystery"], "The Boys": ["Comedy"],
    # horror <-> other
    "Hannibal": ["Crime"], "Stranger Things": ["Horror"], "The Last of Us": ["Horror"],
    "Buffy the Vampire Slayer": ["Horror"], "Angel": ["Horror"],
    "Penny Dreadful": ["Fantasy"], "The Terror": ["Historical"], "Kingdom": ["Historical"],
    "Lovecraft Country": ["Sci-Fi"], "Twin Peaks": ["Horror"],
    "The Returned (Les Revenants)": ["Mystery"],
    # western / historical period crossovers
    "Justified": ["Western"], "The Mandalorian": ["Western"], "Westworld": ["Western"],
    "Deadwood": ["Historical"], "Peaky Blinders": ["Historical"],
    "Boardwalk Empire": ["Historical"], "Babylon Berlin": ["Historical"],
    "Vikings": ["War"], "Rome": ["War"],
    # mystery <-> crime / thriller
    "True Detective": ["Mystery"], "Broadchurch": ["Crime"], "Mare of Easttown": ["Crime"],
    "Sharp Objects": ["Thriller"], "The Sinner": ["Crime"], "Sherlock": ["Crime"],
    "Top of the Lake": ["Crime"], "Severance": ["Mystery"], "Silo": ["Mystery"],
    "Fringe": ["Mystery"], "The X-Files": ["Mystery"], "Lost": ["Mystery"],
    "The OA": ["Mystery"], "The Leftovers": ["Mystery"], "Lupin": ["Mystery"],
    # sci-fi <-> thriller / crime
    "Person of Interest": ["Crime"], "Counterpart": ["Thriller"],
    "Snowpiercer": ["Thriller"], "Black Mirror": ["Thriller"], "Mr. Robot": ["Sci-Fi"],
    "Years and Years": ["Sci-Fi"],
    # crime <-> thriller
    "Breaking Bad": ["Thriller"], "Ozark": ["Thriller"], "Money Heist": ["Thriller"],
    "ZeroZeroZero": ["Thriller"], "Bloodline": ["Thriller"], "Bodyguard": ["Crime"],
    "Your Honor": ["Thriller"], "Banshee": ["Thriller"],
}


def main() -> int:
    catalog = {r["show"] for r in csv.DictReader(open(CATALOG, encoding="utf-8"))}
    primary: dict[str, str] = {}
    dupes = []
    for genre, shows in GENRES.items():
        for s in shows:
            if s in primary:
                dupes.append(s)
            primary[s] = genre

    vocab = set(GENRES)
    errors = []
    for s, extras in SECONDARY.items():
        if s not in catalog:
            errors.append(f"SECONDARY for non-catalog title: {s}")
        for g in extras:
            if g not in vocab:
                errors.append(f"{s}: unknown genre {g!r}")
            if g == primary.get(s):
                errors.append(f"{s}: secondary {g!r} duplicates primary")

    missing = sorted(catalog - primary.keys())
    unknown = sorted(primary.keys() - catalog)
    if dupes or missing or unknown or errors:
        for label, items in [("DUPLICATE", dupes), ("MISSING", missing),
                             ("UNKNOWN", unknown), ("ERRORS", errors)]:
            if items:
                print(f"{label}: {items}", file=sys.stderr)
        return 1

    # Build (show, genre, rank) rows: primary rank 0, then secondaries.
    rows: list[tuple[str, str, int]] = []
    for s in sorted(catalog):
        rows.append((s, primary[s], 0))
        for i, g in enumerate(SECONDARY.get(s, []), start=1):
            rows.append((s, g, i))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["show", "genre", "rank"])
        w.writerows(rows)

    from collections import Counter
    counts = Counter(g for _, g, _ in rows)
    multi = sum(1 for s in catalog if SECONDARY.get(s))
    print(f"wrote {OUT.relative_to(REPO)}: {len(catalog)} shows, {len(rows)} tags "
          f"({multi} multi-genre)")
    print("by genre:", dict(counts.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
