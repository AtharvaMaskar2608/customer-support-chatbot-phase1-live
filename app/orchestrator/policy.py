"""Turn-level policy: message/follow-up caps, sticky-language, escalation blocks.

Limits are read from ``RemoteConfig`` — nothing hardcoded. The escalation surface
(``🎫 Raise a ticket`` / ``📞 Call support``) is the single destination for the
message-cap soft close, the follow-up-cap overflow, and model refusals.
"""

from __future__ import annotations

from app.config.schema import Limits
from app.contracts.router import Language
from app.contracts.wire import (
    Bubble,
    Chip,
    ChipAction,
    ChipActionKind,
    ConversationState,
    RenderBlock,
)
from app.orchestrator.state import ThreadState

# Phase-1 escalation copy (not part of a frozen contract; factual, no advice).
SOFT_CLOSE_TEXT = (
    "We've reached the limit for this chat. To keep going, raise a ticket or call "
    "support and a teammate will pick it up from here."
)
FOLLOW_UP_ESCALATION_TEXT = (
    "I'm still not sure I've got this right. Rather than keep guessing, let me get a "
    "teammate on it."
)
REFUSAL_TEXT = "I can't help with that here — let me get you to a teammate who can."


def escalation_chips() -> list[Chip]:
    """The ticket/call escalation chips (call-support stays available after a ticket)."""
    return [
        Chip(label="🎫 Raise a ticket", action=ChipAction(kind=ChipActionKind.raise_ticket)),
        Chip(label="📞 Call support", action=ChipAction(kind=ChipActionKind.call_support)),
    ]


def escalation_blocks(text: str) -> list[RenderBlock]:
    """A close bubble followed by the escalation chip row."""
    from app.contracts.wire import ChipRow

    return [Bubble(text=text), ChipRow(chips=escalation_chips())]


def is_soft_closed(state: ThreadState, limits: Limits) -> bool:
    """True once the thread has gone past the message cap (soft close on the turn
    that would exceed ``message_cap``)."""
    return state.messages_used > limits.message_cap


def follow_up_would_exceed(state: ThreadState, limits: Limits) -> bool:
    """True when asking one more disambiguation would exceed the ≤2 follow-up cap —
    a third unresolved disambiguation escalates instead of asking again."""
    return state.follow_up_count + 1 > limits.follow_up_cap


def apply_sticky_language(state: ThreadState, detected: Language | None) -> None:
    """§8.5 sticky-language rule. Language is detected on the first user text and
    persisted in thread state; once a turn resolves to English the thread stays
    English thereafter (English is terminal — the lock never reopens)."""
    if state.language_locked:
        return
    if detected is None:
        return
    if state.detected_language is None:
        state.detected_language = detected
    if detected is Language.english:
        state.detected_language = Language.english
        state.language_locked = True


def soft_close(state: ThreadState) -> list[RenderBlock]:
    """Short-circuit the turn to the escalation surface and mark the thread escalated."""
    state.conversation_state = ConversationState.escalated
    return escalation_blocks(SOFT_CLOSE_TEXT)
