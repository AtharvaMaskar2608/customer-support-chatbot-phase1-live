"""Offline LLM fake for the router tests.

``FakeLLMClient`` replays pre-recorded Claude ``tool_use`` blocks keyed by
utterance — never a text completion, never a network call. It mirrors the tiny
slice of ``LLMClient`` the router uses (``complete(...) -> object with .tool_use``),
so injecting it into ``Router`` exercises the exact classification path with a
deterministic, recorded ``route`` tool input.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.contracts.router import ROUTE_TOOL_NAME


class FakeLLMClient:
    """Replays recorded ``route`` tool_use inputs keyed by the user's utterance."""

    def __init__(self, recordings: dict[str, dict[str, Any]]):
        self._recordings = recordings
        self.calls: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        utterance = self._utterance(kwargs)
        if utterance not in self._recordings:
            raise KeyError(f"no recorded route tool_use for utterance: {utterance!r}")
        route_input = self._recordings[utterance]
        return SimpleNamespace(
            tool_use=[SimpleNamespace(name=ROUTE_TOOL_NAME, input=route_input)]
        )

    @staticmethod
    def _utterance(kwargs: dict[str, Any]) -> str:
        messages = kwargs.get("messages") or []
        return messages[-1]["content"] if messages else ""
