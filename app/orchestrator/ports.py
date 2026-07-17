"""Service seams (ports) the orchestrator consumes.

The orchestrator runs in parallel with the router (#3), flow-engine (#2), rag (#4),
ticketing (#12), and store-writer (#13). Those changes' *entrypoints* are not part
of the frozen contracts (only their DATA types are), so this change owns the
Protocols that define the seam. Wave-1 unit tests back them with in-memory fakes;
Wave-2 integration swaps the real modules in behind the same Protocols.

Every port speaks ONLY in frozen contract types (``RouterResult``, ``FlowState``,
``RagAnswer``, ``RaiseTicketInput``/``RaiseTicketResult``, ``TicketStatusInput``/
``TicketStatusResult``, ``TurnRecord``) so neither side redefines a shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

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
from app.contracts.wire import ChipAction, RenderBlock


# ---------------------------------------------------------------------------
# Engine result (flow-engine-runtime #2 entrypoint return; not in frozen contract)
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """What ``EnginePort.step`` returns: the render blocks to emit and the next
    ``FlowState`` to persist (``None`` once the flow completes)."""

    blocks: list[RenderBlock] = field(default_factory=list)
    next_state: FlowState | None = None


# ---------------------------------------------------------------------------
# Internal turn result (orchestrator-only; assembled into a ChatResponse)
# ---------------------------------------------------------------------------


@dataclass
class TurnResult:
    """The outcome of one processed turn before it is shaped into a ChatResponse."""

    blocks: list[RenderBlock] = field(default_factory=list)
    intent: Intent | None = None
    assistant_text: str | None = None
    extracted_params: ExtractedParams | None = None
    retrieval_context: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    escalated: bool = False
    tool_iterations: int = 0


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


@runtime_checkable
class RouterPort(Protocol):
    """llm-router (#3). Executes the forced ``route`` tool_use server-side:
    materializes a ``RouterResult`` from the API-validated ``tool_use.input`` and
    applies the deterministic post-layers (precedence, FY, sticky-language)."""

    def classify(
        self, tool_input: Mapping[str, Any], context: ConversationContext
    ) -> RouterResult: ...


@runtime_checkable
class EnginePort(Protocol):
    """flow-engine-runtime (#2). Deterministic fulfilment: validates windows/FY/
    bytes and assembles the file/data cards. Claude never fabricates report
    content — the engine does."""

    def step(
        self,
        flow_state: FlowState | None,
        intent: Intent,
        params: ExtractedParams,
        action: ChipAction | None = None,
    ) -> StepResult: ...


@runtime_checkable
class RagPort(Protocol):
    """rag-service (#4). Grounded KB answer with citations + retrieval context."""

    def answer(self, query: str, history: Sequence[TurnRef]) -> RagAnswer: ...


@runtime_checkable
class TicketingPort(Protocol):
    """ticketing-freshdesk (#12)."""

    def raise_ticket(self, data: RaiseTicketInput) -> RaiseTicketResult: ...

    def get_ticket_status(self, data: TicketStatusInput) -> TicketStatusResult: ...


@runtime_checkable
class StorePort(Protocol):
    """conversation-store-writer (#13). ``enqueue`` is NON-BLOCKING — the bot
    latency never waits on the DB; a lost row never affects the live conversation."""

    def enqueue(self, record: TurnRecord) -> None: ...


@dataclass
class Services:
    """The tool-binding bundle the agentic loop drives (store is fan-out, held by
    the Orchestrator separately)."""

    router: RouterPort
    engine: EnginePort
    rag: RagPort
    ticketing: TicketingPort
