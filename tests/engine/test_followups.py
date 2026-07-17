"""T5: ≤2 follow-up cap + escalation (proposal §≤2 follow-up enforcement hook)."""

from __future__ import annotations

from app.contracts.wire import Bubble, ChipActionKind, ChipRow

from app.engine.followups import enforce_followups
from tests.engine.conftest import make_ctx


def test_first_two_followups_pass():
    assert enforce_followups(make_ctx(follow_up_count=0, follow_up_cap=2)) is None
    assert enforce_followups(make_ctx(follow_up_count=1, follow_up_cap=2)) is None


def test_third_followup_escalates_with_ticket_and_call_chips():
    esc = enforce_followups(make_ctx(follow_up_count=2, follow_up_cap=2))
    assert esc is not None
    # A bubble + a chip row with exactly the raise-ticket and call-support chips.
    assert any(isinstance(b, Bubble) for b in esc.blocks)
    chip_row = next(b for b in esc.blocks if isinstance(b, ChipRow))
    kinds = {c.action.kind for c in chip_row.chips}
    assert kinds == {ChipActionKind.raise_ticket, ChipActionKind.call_support}


def test_cap_is_read_from_ctx_not_hardcoded():
    # A tightened cap of 1 escalates on the 2nd follow-up.
    assert enforce_followups(make_ctx(follow_up_count=0, follow_up_cap=1)) is None
    assert enforce_followups(make_ctx(follow_up_count=1, follow_up_cap=1)) is not None
