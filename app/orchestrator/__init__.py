"""conversation-orchestrator — the per-turn conversation runtime.

Bootstraps a session, runs the router→dispatch→assemble pipeline (native tool-use
agentic loop for free text; deterministic engine dispatch for structured events),
enforces the message/follow-up caps and the sticky-language rule, owns the live
thread state, and fans out to persistence + tracing.
"""

from __future__ import annotations

from app.orchestrator.agentic import run_agentic_loop
from app.orchestrator.bootstrap import (
    build_config_slice,
    build_session_seed,
    select_greeting,
)
from app.orchestrator.dispatch import dispatch_event
from app.orchestrator.orchestrator import Orchestrator
from app.orchestrator.ports import (
    EnginePort,
    RagPort,
    RouterPort,
    Services,
    StepResult,
    StorePort,
    TicketingPort,
    TurnResult,
)
from app.orchestrator.state import SessionStateStore, ThreadState

__all__ = [
    "Orchestrator",
    "run_agentic_loop",
    "dispatch_event",
    "build_session_seed",
    "build_config_slice",
    "select_greeting",
    "SessionStateStore",
    "ThreadState",
    "Services",
    "StepResult",
    "TurnResult",
    "RouterPort",
    "EnginePort",
    "RagPort",
    "TicketingPort",
    "StorePort",
]
