"""Score a TV show on all eight axes via the Claude API.

Uses Claude Opus 4.8 with adaptive thinking and structured outputs
(``client.messages.parse``) so the model is forced to return a validated
object — no brittle text parsing.
"""
from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-4-8"

Confidence = Literal["low", "medium", "high"]


class AxisScore(BaseModel):
    axis: str = Field(description="Exact axis name, e.g. 'Institutional Sweep'.")
    value: int = Field(ge=0, le=10, description="Integer score 0-10.")
    confidence: Confidence
    justification: str = Field(
        description="One to two sentences, concrete to this specific show."
    )


class ShowScores(BaseModel):
    show: str
    scores: list[AxisScore]


# Scoring rules, lifted from docs/phase-0-claude-code-task.md so the API scorer
# reasons the same way the Phase 0 spike did.
_RULES = """\
Rules:
- Reason from the axis definitions and anchors. Do NOT copy a similar anchor's \
numbers — score each show on its own merits, using the anchors only to calibrate.
- The axes are descriptive, not evaluative, and largely independent. Expect a show \
to score high on some axes and low on others; do not let a show you regard as great \
score high across the board.
- Do not invent facts about a show to sound confident. If you are unsure of the show \
or an axis reading is genuinely borderline, score conservatively and mark confidence low.
- Mind the known traps: propulsion is not speed or action; institutional setting is \
not institutional sweep; a stylized show can still be high on verisimilitude; high \
register is only "corny" when paired with low verisimilitude."""


# Structured-output JSON schema for a ShowScores object. Written by hand (rather
# than ShowScores.model_json_schema()) so it carries no numeric constraints, which
# the output_config.format API rejects. Range 0-10 is enforced by Pydantic after.
SHOW_SCORES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["show", "scores"],
    "properties": {
        "show": {"type": "string"},
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["axis", "value", "confidence", "justification"],
                "properties": {
                    "axis": {"type": "string"},
                    "value": {"type": "integer"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "justification": {"type": "string"},
                },
            },
        },
    },
}

_SYSTEM_INSTRUCTION = (
    "You are scoring TV shows for Show Type. Read this rubric in full — the "
    "eight axis definitions, the scoring conventions, the calibration anchors, and "
    "the worked examples — then score shows strictly from it.\n\n"
)


def _system_blocks(rubric_text: str) -> list[dict]:
    # Cache the rubric prefix so batch/sequential scoring of many shows reuses it.
    return [
        {
            "type": "text",
            "text": _SYSTEM_INSTRUCTION + rubric_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _user_prompt(title: str, axis_names: list[str]) -> str:
    axis_list = ", ".join(axis_names)
    return (
        f'Score the TV show "{title}" on all eight axes defined in the rubric above.\n\n'
        f"Return one entry per axis, using these exact axis names: {axis_list}.\n"
        "For each axis produce an integer value 0-10, a confidence of low/medium/high, "
        "and a one-to-two sentence justification that names the specific thing in the "
        "show driving the score (no generic phrasing).\n\n"
        f"{_RULES}"
    )


def score_show(
    title: str,
    rubric_text: str,
    axis_names: list[str],
    *,
    client: anthropic.Anthropic | None = None,
    model: str = MODEL,
) -> ShowScores:
    """Score `title` on the eight axes. Returns a validated ShowScores.

    Requires ANTHROPIC_API_KEY in the environment (or a pre-built `client`).
    """
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=_system_blocks(rubric_text),
        messages=[{"role": "user", "content": _user_prompt(title, axis_names)}],
        output_format=ShowScores,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(
            f"model did not return a valid score object (stop_reason="
            f"{response.stop_reason})"
        )
    return parsed


def build_batch_params(
    title: str, rubric_text: str, axis_names: list[str], model: str = MODEL
) -> dict:
    """Params for one Batches-API request that scores `title`."""
    return {
        "model": model,
        "max_tokens": 4096,
        "thinking": {"type": "adaptive"},
        "system": _system_blocks(rubric_text),
        "messages": [{"role": "user", "content": _user_prompt(title, axis_names)}],
        "output_config": {"format": {"type": "json_schema", "schema": SHOW_SCORES_SCHEMA}},
    }


def parse_message_scores(message) -> ShowScores:
    """Extract a validated ShowScores from a (possibly thinking-prefixed) message."""
    text = next((b.text for b in message.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError(f"no text block in message (stop_reason={message.stop_reason})")
    return ShowScores.model_validate_json(text)
