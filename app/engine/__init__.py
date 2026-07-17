"""Flow-engine runtime — the single, flow-agnostic deterministic executor over the
frozen flow-engine-contract. No LLM calls, no HTTP transport, no rendering: it
drives the frozen ``FlowState``/``Step`` state machine, enforces the date-window /
FY / follow-up guardrails from each flow's frozen config, owns the byte-validation
retry policy + selection cache, assembles delivery blocks, and maps faults to the
frozen error taxonomy.

Public surface (re-exported here) is grown task-by-task; see ``tasks.md``.
"""

from __future__ import annotations

from app.engine.events import (
    DateSelected,
    FlowEvent,
    FollowUp,
    ParamSelected,
    ReopenStep,
    Resend,
)
from app.engine.faults import (
    FinXAuthError,
    FinXFetchError,
    FinXTimeoutError,
    FinXTransportError,
)
from app.engine.ports import (
    ByteFetcher,
    CachePort,
    EmailResult,
    EngineContext,
    FlowDefinition,
    GenerationError,
    GenerationResult,
    NoData,
    ReportBytes,
    ReportUrl,
)
from app.engine.results import (
    Escalation,
    EYearError,
    FlowStepResult,
    FYResolved,
)

__all__ = [
    # events
    "FlowEvent",
    "ParamSelected",
    "DateSelected",
    "Resend",
    "ReopenStep",
    "FollowUp",
    # faults
    "FinXAuthError",
    "FinXFetchError",
    "FinXTimeoutError",
    "FinXTransportError",
    # ports
    "ByteFetcher",
    "CachePort",
    "EngineContext",
    "FlowDefinition",
    "GenerationResult",
    "ReportUrl",
    "ReportBytes",
    "EmailResult",
    "NoData",
    "GenerationError",
    # results
    "FlowStepResult",
    "Escalation",
    "FYResolved",
    "EYearError",
]
