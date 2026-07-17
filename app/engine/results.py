"""Engine result types — the deterministic outputs of the runtime functions.

None of these are wire types; they carry frozen ``RenderBlock``s plus the next
``FlowState`` the caller (the orchestrator) persists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contracts.flow import FlowState
from app.contracts.wire import ConversationState, RenderBlock


@dataclass
class FlowStepResult:
    """One ``advance`` step's outcome: the next ``FlowState``, the ordered render
    blocks to emit, the coarse conversation state, and whether the turn escalated."""

    state: FlowState
    blocks: list[RenderBlock] = field(default_factory=list)
    conversation_state: ConversationState = ConversationState.collecting
    escalated: bool = False


@dataclass
class Escalation:
    """The escalation affordance emitted at the follow-up cap: a bubble plus the
    raise-ticket / call-support recovery chips."""

    blocks: list[RenderBlock] = field(default_factory=list)


@dataclass(frozen=True)
class FYResolved:
    """A financial year resolved into the API long form (``"YYYY-YYYY"``)."""

    fy_long: str


@dataclass(frozen=True)
class EYearError:
    """An out-of-window financial year — maps to E-YEAR with NO adapter call. Carries
    the supported FYs so the error bubble can render the three recovery chips."""

    requested: str | None
    supported: tuple[str, ...]
