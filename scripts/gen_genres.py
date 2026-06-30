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


def main() -> int:
    catalog = {r["show"] for r in csv.DictReader(open(CATALOG, encoding="utf-8"))}
    mapping: dict[str, str] = {}
    dupes = []
    for genre, shows in GENRES.items():
        for s in shows:
            if s in mapping:
                dupes.append(s)
            mapping[s] = genre

    missing = sorted(catalog - mapping.keys())   # catalog shows with no genre
    unknown = sorted(mapping.keys() - catalog)    # genres for non-catalog titles
    if dupes or missing or unknown:
        if dupes:
            print("DUPLICATE assignments:", dupes, file=sys.stderr)
        if missing:
            print(f"MISSING genre for {len(missing)}:", missing, file=sys.stderr)
        if unknown:
            print(f"UNKNOWN titles (not in catalog) {len(unknown)}:", unknown, file=sys.stderr)
        return 1

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["show", "genre"])
        for s in sorted(mapping):
            w.writerow([s, mapping[s]])
    counts = {g: len(v) for g, v in sorted(GENRES.items(), key=lambda kv: -len(kv[1]))}
    print(f"wrote {OUT.relative_to(REPO)}: {len(mapping)} shows")
    print("by genre:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
