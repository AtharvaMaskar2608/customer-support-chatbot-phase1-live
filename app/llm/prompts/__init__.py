"""Externalized router prompts (llm-router capability).

Per spec §2.2 ("prompts externalized, not in code"), the router's system prompt,
intent taxonomy + §2.5 precedence guidance, parameter-extraction guidance,
one-shot follow-up guidance, few-shot examples, and the CG / Tax-P&L education
lines are versioned files on disk loaded at runtime — never inlined in
``router.py``. This module is the loader.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.contracts.router import Intent

_DIR = Path(__file__).parent

#: The markdown sections assembled, in order, into the router system prompt.
_SYSTEM_PARTS: tuple[str, ...] = (
    "system.md",
    "intent_taxonomy.md",
    "param_extraction.md",
    "follow_up.md",
)


def _read_text(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def few_shots() -> list[dict[str, Any]]:
    """The few-shot ``{utterance, route_input}`` examples (EN/HI/Hinglish/typos)."""
    return json.loads(_read_text("few_shots.json"))


@lru_cache(maxsize=1)
def _education_lines() -> dict[str, str]:
    return json.loads(_read_text("education_lines.json"))


def education_line(intent: Intent) -> str | None:
    """The externalized CG / Tax-P&L education prefix for ``intent`` (``None`` for
    every other intent). The set of intents that carry a line is the frozen
    ``EDUCATION_LINE_INTENTS``; the copy lives in ``education_lines.json``."""
    return _education_lines().get(intent.value)


def _render_few_shots(examples: list[dict[str, Any]]) -> str:
    lines = ["# Few-shot examples", ""]
    for ex in examples:
        lines.append(f"User: {ex['utterance']}")
        lines.append(f"route({json.dumps(ex['route_input'], ensure_ascii=False)})")
        lines.append("")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    """Assemble the full router system prompt from the versioned prompt files at
    runtime. Includes the complete 16-value intent taxonomy, the §2.5 precedence
    guidance, parameter-extraction + follow-up guidance, and the few-shot block."""
    parts = [_read_text(name) for name in _SYSTEM_PARTS]
    parts.append(_render_few_shots(few_shots()))
    return "\n\n".join(part.strip() for part in parts) + "\n"


__all__ = ["load_system_prompt", "few_shots", "education_line"]
