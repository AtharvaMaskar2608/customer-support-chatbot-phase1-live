"""Flow-engine runtime — the single, flow-agnostic deterministic executor over the
frozen flow-engine-contract. No LLM calls, no HTTP transport, no rendering: it
drives the frozen ``FlowState``/``Step`` state machine, enforces the date-window /
FY / follow-up guardrails from each flow's frozen config, owns the byte-validation
retry policy + selection cache, assembles delivery blocks, and maps faults to the
frozen error taxonomy.

Public surface (re-exported here) is grown task-by-task; see ``tasks.md``.
"""

from __future__ import annotations

from app.engine.calendar import build_calendar, out_of_range_nudge, validate_range
from app.engine.cache import SelectionCache
from app.engine.delivery import deliver, mask_email
from app.engine.errors import map_error
from app.engine.events import (
    Confirm,
    DateSelected,
    FlowEvent,
    FollowUp,
    ParamSelected,
    ReopenStep,
    Resend,
)
from app.engine.executor import advance
from app.engine.followups import enforce_followups
from app.engine.fy import resolve_fy
from app.engine.registry import FlowRegistry, discover
from app.engine.steps import (
    build_stepper_card,
    materialize_steps,
    next_step,
    reopen_step,
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
    "Confirm",
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
    # engine functions
    "advance",
    "next_step",
    "reopen_step",
    "materialize_steps",
    "build_stepper_card",
    "build_calendar",
    "validate_range",
    "out_of_range_nudge",
    "resolve_fy",
    "enforce_followups",
    "deliver",
    "mask_email",
    "map_error",
    "SelectionCache",
    "FlowRegistry",
    "discover",
]
