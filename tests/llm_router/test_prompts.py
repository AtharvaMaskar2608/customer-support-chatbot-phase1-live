"""Task 1 — externalized prompts are on disk and loadable at runtime (spec §2.2).

Asserts the prompt loader assembles a system prompt covering the full 16-value
intent taxonomy, exposes few-shots, and produces CG / Tax-P&L education lines
from externalized copy (and nothing else). No LLM, no network.
"""

from __future__ import annotations

from pathlib import Path

from app.contracts.router import EDUCATION_LINE_INTENTS, Intent
from app.llm.prompts import education_line, few_shots, load_system_prompt

_PROMPT_DIR = Path("app/llm/prompts")


def test_prompt_files_exist_on_disk():
    # Externalized, not inlined: the versioned assets are real files.
    for name in (
        "system.md",
        "intent_taxonomy.md",
        "param_extraction.md",
        "follow_up.md",
        "few_shots.json",
        "education_lines.json",
    ):
        assert (_PROMPT_DIR / name).is_file(), name


def test_system_prompt_covers_every_intent():
    prompt = load_system_prompt()
    assert isinstance(prompt, str) and prompt.strip()
    # The taxonomy names every one of the 16 frozen intents.
    for intent in Intent:
        assert intent.value in prompt, intent.value


def test_few_shots_span_languages():
    langs = {ex["route_input"]["detected_language"] for ex in few_shots()}
    assert {"english", "hindi", "hinglish"} <= langs


def test_education_line_only_for_cg_and_tax_pnl():
    for intent in Intent:
        line = education_line(intent)
        if intent in EDUCATION_LINE_INTENTS:
            assert line and isinstance(line, str)
        else:
            assert line is None
