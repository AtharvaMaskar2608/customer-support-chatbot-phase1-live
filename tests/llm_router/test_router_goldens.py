"""Task 7 — end-to-end golden replay (offline).

Replays every recorded ``route`` tool_use block through the full ``Router`` and
asserts the final ``RouterResult`` matches the golden. The set spans
English/Hindi/Hinglish/typos and covers §2.5 precedence, AY→FY confirmation,
one-shot follow-ups + cap escalation, and sticky-language — with NO network.
"""

from __future__ import annotations

import pytest

from app.contracts.router import ConversationContext, RouterResult
from app.llm.router import Router
from tests.llm_router.fakes import FakeLLMClient


def _ctx(overrides: dict) -> ConversationContext:
    base = dict(
        user_id="X008593",
        session_id="s",
        access_token="t",
        platform="web",
        page="support",
    )
    base.update(overrides or {})
    return ConversationContext(**base)


def test_every_golden_has_a_recording(goldens, recordings):
    missing = sorted({c["utterance"] for c in goldens} - set(recordings))
    assert not missing, f"goldens without a recording: {missing}"


def test_goldens_replay_end_to_end(goldens, recordings):
    fake = FakeLLMClient(recordings)
    failures = []
    for case in goldens:
        result = Router(client=fake).route(case["utterance"], _ctx(case.get("ctx", {})))
        expected = RouterResult.model_validate(case["expected"])
        if result != expected:
            failures.append(
                f"[{case['name']}] {case['utterance']!r}\n"
                f"  expected: {expected.model_dump()}\n"
                f"  actual:   {result.model_dump()}"
            )
    assert not failures, "golden mismatches:\n" + "\n".join(failures)


@pytest.mark.parametrize(
    "name",
    [
        "precedence-tax-beats-pnl",
        "precedence-capital-gain",
        "precedence-holding-not-ledger",
        "ay-to-fy-confirmation",
        "follow-up-cap-escalates",
        "sticky-language-locked-forces-english",
        "hindi-unlocked",
        "hinglish-capital-gain",
        "mtf-ledger-survives-base-token",
        "rag-not-forced-to-report",
    ],
)
def test_donecondition_dimensions_present(goldens, name):
    # The doneCondition names each of these behaviours; assert the golden set
    # actually exercises them (guards against silently dropping coverage).
    assert any(c["name"] == name for c in goldens), name
