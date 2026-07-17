"""Task 7 — transport-failure fallback (offline).

Confirms the single defined error path: an API/transport failure (or a response
with no ``route`` block) returns the frozen ``transport_failure_result()`` and
never raises to the caller. There is no JSON-repair step — strict tool use makes
a successful response API-validated.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.contracts.router import ConversationContext, Intent, transport_failure_result
from app.llm.router import route


def _ctx() -> ConversationContext:
    return ConversationContext(
        user_id="X008593", session_id="s", access_token="t", platform="web", page="support"
    )


class _RaisingClient:
    def complete(self, **kwargs):
        raise ConnectionError("upstream unavailable")


class _NoToolBlockClient:
    def complete(self, **kwargs):
        return SimpleNamespace(tool_use=[])


def test_transport_error_returns_frozen_fallback():
    result = route("get my p&l", _ctx(), client=_RaisingClient())
    assert result == transport_failure_result()
    assert result.intent is Intent.smalltalk_fallback and result.escalate is True


def test_missing_route_block_returns_frozen_fallback():
    result = route("get my p&l", _ctx(), client=_NoToolBlockClient())
    assert result == transport_failure_result()
