"""Phase-1 in-memory adapters wired by ``app/main.py``.

Wave-1 scope: the orchestrator runs end-to-end behind the frozen interfaces with
in-memory stand-ins; the real router (#3) / flow-engine (#2) / rag (#4) /
ticketing (#12) / store-writer (#13) swap in at Wave 2. These stand-ins are honest
placeholders — no fabricated report content — and make NO network/DB calls.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Sequence

from app.contracts.flow import FlowState
from app.contracts.rag import RagAnswer, RefusalReason
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
from app.contracts.wire import Bubble, ChipAction
from app.orchestrator.ports import StepResult


class InMemoryStore:
    """Non-blocking store stand-in — records enqueued turns in a list."""

    def __init__(self) -> None:
        self.records: list[TurnRecord] = []

    def enqueue(self, record: TurnRecord) -> None:
        self.records.append(record)


class DefaultRouter:
    """Materializes a ``RouterResult`` from the API-validated ``route`` tool input
    (the ``route`` tool's input_schema IS ``RouterResult``). The real deterministic
    post-layers land with llm-router (#3)."""

    def classify(self, tool_input: Mapping[str, Any], context: ConversationContext) -> RouterResult:
        try:
            return RouterResult.model_validate(dict(tool_input))
        except Exception:
            return RouterResult(intent=Intent.smalltalk_fallback)


class DefaultEngine:
    """Phase-1 engine stand-in: acknowledges the intent without fabricating report
    content. The real fulfilment engine lands with flow-engine-runtime (#2)."""

    def step(
        self,
        flow_state: FlowState | None,
        intent: Intent,
        params: ExtractedParams,
        action: ChipAction | None = None,
    ) -> StepResult:
        return StepResult(
            blocks=[Bubble(text="I'm getting that ready — full report delivery is being wired in.")],
            next_state=flow_state,
        )


class DefaultRag:
    """Phase-1 RAG stand-in: refuses cleanly until rag-service (#4) lands."""

    def answer(self, query: str, history: Sequence[TurnRef]) -> RagAnswer:
        return RagAnswer(
            answer="I can't answer that from my knowledge base yet.",
            refused=True,
            refusal_reason=RefusalReason.no_relevant_context,
        )


class DefaultTicketing:
    """Phase-1 ticketing stand-in: mints a local ticket id until ticketing (#12) lands."""

    def raise_ticket(self, data: RaiseTicketInput) -> RaiseTicketResult:
        return RaiseTicketResult(ticket_id=f"T-{uuid.uuid4().hex[:8]}", status="open")

    def get_ticket_status(self, data: TicketStatusInput) -> TicketStatusResult:
        return TicketStatusResult(ticket_id=data.ticket_ref, status="open")
