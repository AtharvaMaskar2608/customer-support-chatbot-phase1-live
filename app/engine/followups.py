"""≤2 follow-up cap + escalation (proposal §≤2 follow-up enforcement hook).

The router decides WHETHER a turn is a follow-up; the engine enforces the CAP and
the escalation transition. After the cap's worth of unresolved follow-ups the
engine stops asking and emits the escalation affordance (raise-ticket / call-support
chips).
"""

from __future__ import annotations

from app.contracts.wire import Bubble, ChipRow

from app.engine.chips import call_support_chip, raise_ticket_chip
from app.engine.ports import EngineContext
from app.engine.results import Escalation

#: Engine-default escalation copy (no frozen taxonomy entry for the cap message).
#: [CONFIRM: final copy is a product/flow concern.]
ESCALATION_TEXT = "I'm not able to sort this out over chat — let me get you to a human who can."


def enforce_followups(ctx: EngineContext) -> Escalation | None:
    """Return an ``Escalation`` when a further follow-up would exceed the cap, else
    ``None``. With ``follow_up_count`` = unresolved follow-ups already asked and the
    default cap of 2: counts 0 and 1 pass (ask the 1st/2nd), count 2 escalates (the
    3rd stops asking)."""
    if ctx.follow_up_count >= ctx.follow_up_cap:
        return Escalation(
            blocks=[
                Bubble(text=ESCALATION_TEXT),
                ChipRow(chips=[raise_ticket_chip(), call_support_chip()]),
            ]
        )
    return None
