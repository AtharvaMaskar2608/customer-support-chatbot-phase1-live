"""Live per-thread conversation state + the Phase-1 in-memory store.

This is the LIVE read path, keyed by ``thread_id``. It is deliberately separate
from the store-writer table (which is async, write-only, analytics/fine-tuning — a
lost row there never affects the live conversation). Phase-1 is a single-process
dict; a Redis/DB-backed store is a later swap behind the same ``SessionStateStore``
interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.contracts.flow import FlowState
from app.contracts.router import ConversationContext, Language, TurnRef
from app.contracts.wire import ConversationState


@dataclass
class ThreadState:
    """Everything needed to resume a conversation deterministically.

    ``messages`` is the Anthropic-format running transcript the agentic loop feeds
    back to Claude. ``history`` is the lighter per-turn reference list handed to the
    router/RAG. ``messages_used`` counts user turns for the message cap;
    ``follow_up_count`` counts consecutive disambiguations for the follow-up cap.
    """

    thread_id: str
    user_id: str
    session_id: str
    access_token: str
    platform: str
    page: str
    is_dark_theme: bool = False

    turn_number: int = 0
    messages_used: int = 0
    follow_up_count: int = 0

    detected_language: Language | None = None
    language_locked: bool = False

    flow_state: FlowState | None = None
    conversation_state: ConversationState = ConversationState.greeting

    messages: list[dict[str, Any]] = field(default_factory=list)
    history: list[TurnRef] = field(default_factory=list)

    def to_context(self) -> ConversationContext:
        """Build the frozen ``ConversationContext`` the router/pipeline consume."""
        return ConversationContext(
            user_id=self.user_id,
            session_id=self.session_id,
            access_token=self.access_token,
            is_dark_theme=self.is_dark_theme,
            platform=self.platform,
            page=self.page,
            history=list(self.history),
            turn_number=self.turn_number,
            follow_up_count=self.follow_up_count,
            detected_language=self.detected_language,
            language_locked=self.language_locked,
        )


class SessionStateStore:
    """Phase-1 in-memory ``thread_id`` → ``ThreadState`` store."""

    def __init__(self) -> None:
        self._threads: dict[str, ThreadState] = {}

    def get(self, thread_id: str) -> ThreadState | None:
        return self._threads.get(thread_id)

    def put(self, thread_id: str, state: ThreadState) -> None:
        self._threads[thread_id] = state
