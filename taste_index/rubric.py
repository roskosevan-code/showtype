"""Parse the eight axis definitions out of docs/rubric.md.

The rubric is the single source of truth: the axes are *seeded verbatim* into
the `axis` table, and the full rubric text is handed to the scorer as context.
Revise the rubric, not this code, when an axis is mis-reading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Matches an axis heading like "### 1. Propulsion" or
# "### 4. Interiority (Depth)". The canonical name is the part before any "(".
_AXIS_HEADING = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")


@dataclass(frozen=True)
class Axis:
    position: int      # 1..8
    name: str          # canonical short name, e.g. "Interiority"
    slug: str          # kebab-case, e.g. "institutional-sweep"
    definition: str    # verbatim section text from the rubric


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_axes(rubric_text: str) -> list[Axis]:
    """Extract the eight axes from the '## The eight axes' section.

    Each axis spans from its '### N. Name' heading up to the next '###' axis
    heading or the next '## ' section heading.
    """
    axes: list[Axis] = []
    current_heading: re.Match[str] | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_heading is None:
            return
        raw = current_heading.group(2).strip()
        name = raw.split("(")[0].strip()
        axes.append(
            Axis(
                position=int(current_heading.group(1)),
                name=name,
                slug=_slugify(name),
                definition="\n".join(current_lines).strip(),
            )
        )

    for line in rubric_text.splitlines():
        heading = _AXIS_HEADING.match(line)
        if heading:
            flush()
            current_heading, current_lines = heading, [line]
        elif current_heading is not None:
            if line.startswith("## "):  # reached the next top-level section
                flush()
                current_heading, current_lines = None, []
            else:
                current_lines.append(line)
    flush()

    if len(axes) != 8:
        raise ValueError(
            f"expected 8 axes in the rubric, found {len(axes)}: "
            f"{[a.name for a in axes]}"
        )
    return axes


def load_rubric(path: str | Path) -> tuple[str, list[Axis]]:
    """Return (full rubric text, parsed axes) for the rubric at `path`."""
    text = Path(path).read_text(encoding="utf-8")
    return text, parse_axes(text)
