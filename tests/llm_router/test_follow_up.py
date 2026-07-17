"""Task 5 — one-shot follow-up + follow-up-cap escalation (no LLM).

Drives ``_resolve_follow_up`` directly. Confirms the router reads the cross-turn
``follow_up_count`` and escalates at the remote-config cap without ever
incrementing the count itself.
"""

from __future__ import annotations

from app.config.schema import Limits
from app.contracts.router import ConversationContext
from app.llm.router import DEFAULT_FOLLOW_UP_CAP, _resolve_follow_up


def _ctx(follow_up_count: int) -> ConversationContext:
    return ConversationContext(
        user_id="X008593",
        session_id="s",
        access_token="t",
        platform="web",
        page="support",
        follow_up_count=follow_up_count,
    )


def test_cap_default_matches_remote_config():
    assert DEFAULT_FOLLOW_UP_CAP == Limits().follow_up_cap == 2


def test_below_cap_passes_model_follow_up_through():
    ctx = _ctx(follow_up_count=0)
    follow_up, escalate = _resolve_follow_up(ctx, "Which report do you need?", False)
    assert follow_up == "Which report do you need?"
    assert escalate is False
    # The router never mutates the cross-turn count.
    assert ctx.follow_up_count == 0


def test_at_cap_suppresses_follow_up_and_escalates():
    ctx = _ctx(follow_up_count=2)
    follow_up, escalate = _resolve_follow_up(ctx, "Which report do you need?", False)
    assert follow_up is None
    assert escalate is True


def test_above_cap_also_escalates():
    ctx = _ctx(follow_up_count=3)
    assert _resolve_follow_up(ctx, None, False) == (None, True)


def test_model_escalate_respected_below_cap():
    ctx = _ctx(follow_up_count=0)
    follow_up, escalate = _resolve_follow_up(ctx, None, True)
    assert escalate is True
    assert follow_up is None
