"""In-memory fakes + scripted-LLM helpers for the orchestrator unit tests.

Everything the orchestrator consumes (router / engine / rag / ticketing / store) is
behind a frozen-typed port; these fakes back those ports so the suite runs offline —
no live FinX/Freshdesk, no DB, no real LLM call. The ``FakeLLM`` returns scripted
``LLMResponse`` objects so tests drive the ``stop_reason`` state machine directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.contracts.flow import FlowState
from app.contracts.rag import RagAnswer
from app.contracts.router import (
    ConversationContext,
    ExtractedParams,
    Intent,
    RaiseTicketInput,
    RaiseTicketResult,
    RouterResult,
    TicketStatusInput,
    TicketStatusResult,
    TurnRef,
)
from app.contracts.store import TurnRecord
from app.contracts.wire import ChipAction
from app.llm.client import LLMConfig, LLMResponse, Usage
from app.orchestrator.ports import StepResult


# ---------------------------------------------------------------------------
# Scripted LLM
# ---------------------------------------------------------------------------


@dataclass
class FakeToolUse:
    """A minimal stand-in for an Anthropic ``tool_use`` content block."""

    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    type: str = "tool_use"


class FakeLLM:
    """Returns queued ``LLMResponse`` objects in order; repeats the last one when the
    queue is exhausted (so an "always tool_use" script drives the iteration cap).
    Raises if called with nothing to return — doubles as a "no LLM call" guard."""

    def __init__(self, responses: Sequence[LLMResponse] | None = None) -> None:
        self._responses = list(responses or [])
        self._last: LLMResponse | None = None
        self.config = LLMConfig()
        self.calls: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        if self._responses:
            self._last = self._responses.pop(0)
        elif self._last is None:
            raise AssertionError("FakeLLM.complete called with no scripted response")
        return self._last


def tool_use_response(*tool_uses: FakeToolUse) -> LLMResponse:
    blocks = list(tool_uses)
    return LLMResponse(
        text="", usage=Usage(1, 1), stop_reason="tool_use", content=blocks, tool_use=blocks
    )


def end_turn_response(text: str = "Done.") -> LLMResponse:
    return LLMResponse(text=text, usage=Usage(1, 1), stop_reason="end_turn", content=[], tool_use=[])


def refusal_response() -> LLMResponse:
    return LLMResponse(text="", usage=Usage(1, 1), stop_reason="refusal", content=[], tool_use=[])


def pause_turn_response() -> LLMResponse:
    return LLMResponse(text="", usage=Usage(1, 1), stop_reason="pause_turn", content=[], tool_use=[])


def route_block(input: dict[str, Any] | None = None, id: str = "tu_route") -> FakeToolUse:
    return FakeToolUse(id=id, name="route", input=input or {"intent": "rag_qa"})


# ---------------------------------------------------------------------------
# Service fakes
# ---------------------------------------------------------------------------


class FakeRouter:
    """Returns a fixed ``RouterResult`` (ignores tool_input — the classification is
    scripted by the test); records the calls."""

    def __init__(self, result: RouterResult) -> None:
        self.result = result
        self.calls: list[tuple[dict[str, Any], ConversationContext]] = []

    def classify(self, tool_input: Mapping[str, Any], context: ConversationContext) -> RouterResult:
        self.calls.append((dict(tool_input), context))
        return self.result


class FakeEngine:
    def __init__(self, result: StepResult) -> None:
        self.result = result
        self.calls: list[tuple[Any, Intent, ExtractedParams, Any]] = []

    def step(self, flow_state, intent, params, action=None) -> StepResult:
        self.calls.append((flow_state, intent, params, action))
        return self.result


class FailingEngine:
    """Raises inside ``step`` so the loop must surface an ``is_error`` tool_result."""

    def __init__(self) -> None:
        self.calls = 0

    def step(self, flow_state, intent, params, action=None) -> StepResult:
        self.calls += 1
        raise RuntimeError("engine boom")


class FakeRag:
    def __init__(self, answer: RagAnswer) -> None:
        self._answer = answer
        self.calls: list[tuple[str, list[TurnRef]]] = []

    def answer(self, query: str, history: Sequence[TurnRef]) -> RagAnswer:
        self.calls.append((query, list(history)))
        return self._answer


class FakeTicketing:
    def __init__(self, ticket_id: str = "T-777", status: str = "open") -> None:
        self.ticket_id = ticket_id
        self.status = status
        self.raised: list[RaiseTicketInput] = []
        self.status_lookups: list[TicketStatusInput] = []

    def raise_ticket(self, data: RaiseTicketInput) -> RaiseTicketResult:
        self.raised.append(data)
        return RaiseTicketResult(ticket_id=self.ticket_id, status=self.status)

    def get_ticket_status(self, data: TicketStatusInput) -> TicketStatusResult:
        self.status_lookups.append(data)
        return TicketStatusResult(ticket_id=data.ticket_ref, status="in_progress")


class FakeStore:
    def __init__(self) -> None:
        self.records: list[TurnRecord] = []

    def enqueue(self, record: TurnRecord) -> None:
        self.records.append(record)
