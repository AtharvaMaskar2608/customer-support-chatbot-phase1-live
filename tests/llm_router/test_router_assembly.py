"""Task 6 — classifier wiring + route() assembly.

Uses a minimal inline fake ``LLMClient`` (the reusable ``FakeLLMClient`` and the
golden replay harness land in Task 7). Confirms the forced-tool contract, the
transport-failure fallback, and deterministic education-line assignment.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.contracts.router import ROUTE_TOOL_CHOICE, ConversationContext, Intent
from app.llm.router import Router, route


def _route_input(**overrides) -> dict:
    payload = {
        "intent": "report_pnl",
        "extracted_params": {
            "fy": None,
            "date_range": None,
            "segment": None,
            "report_format": None,
            "delivery": None,
        },
        "needs_confirmation": False,
        "follow_up_question": None,
        "detected_language": "english",
        "escalate": False,
        "education_line": None,
    }
    payload.update(overrides)
    return payload


class _RecordingClient:
    """Captures the request and returns a canned route tool_use block."""

    def __init__(self, route_input: dict):
        self._route_input = route_input
        self.calls: list[dict] = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            tool_use=[SimpleNamespace(name="route", input=self._route_input)]
        )


class _RaisingClient:
    def complete(self, **kwargs):
        raise RuntimeError("transport down")


def _ctx() -> ConversationContext:
    return ConversationContext(
        user_id="X008593", session_id="s", access_token="t", platform="web", page="support"
    )


def test_route_issues_one_forced_route_tool_call():
    client = _RecordingClient(_route_input())
    route("get my p&l", _ctx(), client=client)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["tool_choice"] == ROUTE_TOOL_CHOICE
    names = [t["name"] for t in call["tools"]]
    assert names == ["route"]
    assert call["tools"][0]["strict"] is True
    assert call["system"]  # externalized system prompt supplied


def test_transport_failure_returns_fallback():
    result = route("get my p&l", _ctx(), client=_RaisingClient())
    assert result.intent is Intent.smalltalk_fallback
    assert result.escalate is True


def test_missing_route_block_returns_fallback():
    empty = SimpleNamespace(tool_use=[])

    class _EmptyClient:
        def complete(self, **kwargs):
            return empty

    result = route("get my p&l", _ctx(), client=_EmptyClient())
    assert result.intent is Intent.smalltalk_fallback
    assert result.escalate is True


def test_education_line_only_for_tax_flow_specializations():
    cg = route(
        "capital gain report",
        _ctx(),
        client=_RecordingClient(_route_input(intent="report_capital_gain")),
    )
    assert cg.intent is Intent.report_capital_gain
    assert cg.education_line  # set from externalized copy

    pnl = route("get my p&l", _ctx(), client=_RecordingClient(_route_input()))
    assert pnl.intent is Intent.report_pnl
    assert pnl.education_line is None


def test_router_class_injectable_client():
    router = Router(client=_RecordingClient(_route_input(intent="report_ledger")))
    result = router.route("show my ledger", _ctx())
    assert result.intent is Intent.report_ledger
