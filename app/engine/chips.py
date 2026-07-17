"""Recovery-chip factories shared by escalation and error mapping.

Chip LABELS coming from the frozen error taxonomy are preserved VERBATIM; only the
typed ``ChipAction`` is inferred here (the action kind is not part of the frozen
copy). ``fy_chip`` builds the FY selection chips whose payload carries the long-form
year the widget echoes back.
"""

from __future__ import annotations

from app.contracts.flow import fy_long_to_short
from app.contracts.wire import Chip, ChipAction, ChipActionKind


def _infer_kind(label: str) -> ChipActionKind:
    low = label.lower()
    if "ticket" in low:
        return ChipActionKind.raise_ticket
    if "call" in low:
        return ChipActionKind.call_support
    if "retry" in low or "try again" in low or "↺" in label:
        return ChipActionKind.retry
    if "email" in low or "✉" in label:
        return ChipActionKind.email
    if "excel" in low or "📊" in label:
        return ChipActionKind.retry  # "Get Excel here" — re-deliver as Excel in-chat
    if low.startswith("try fy"):
        return ChipActionKind.select_param
    return ChipActionKind.send_text


def chip_for_label(label: str, *, payload: dict[str, str] | None = None) -> Chip:
    """A recovery chip with its label kept verbatim and a typed action inferred."""
    return Chip(label=label, action=ChipAction(kind=_infer_kind(label), payload=payload or {}))


def fy_chip(fy_long: str) -> Chip:
    """A ``select_param`` chip for an in-window FY: short label, long-form payload."""
    return Chip(
        label=fy_long_to_short(fy_long),
        action=ChipAction(kind=ChipActionKind.select_param, payload={"fy": fy_long}),
    )


def raise_ticket_chip(label: str = "🎫 Raise a ticket") -> Chip:
    return chip_for_label(label)


def call_support_chip(label: str = "📞 Call support") -> Chip:
    return chip_for_label(label)
