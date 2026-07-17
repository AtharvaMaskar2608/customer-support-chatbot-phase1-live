"""The conversation orchestrator — one user turn → one ordered render-block array.

``handle_turn`` loads thread state, increments the turn, enforces the message cap,
branches free-text (agentic loop) vs structured event (deterministic dispatch),
assembles the ``ChatResponse``, wraps the whole turn in the tracing root ``agent``
span (``thread_id``/``user_id`` stitched on), and fans the completed turn out to the
store-writer via non-blocking ``enqueue`` — the response never awaits the DB write.

The first turn (``thread_id`` absent) is the session seed (bootstrap); ``thread_id``
is minted once there and echoed on every subsequent turn.
"""

from __future__ import annotations

import uuid

from app.config.schema import RemoteConfig
from app.contracts.router import TurnRef
from app.contracts.store import TurnRecord
from app.contracts.tracing import SpanType, trace_manager
from app.contracts.wire import (
    Bubble,
    Caps,
    ChatRequest,
    ChatResponse,
    ChipActionKind,
    ConversationState,
    SessionContext,
)
from app.llm.client import LLMClient
from app.orchestrator.agentic import run_agentic_loop
from app.orchestrator.bootstrap import build_session_seed
from app.orchestrator.dispatch import dispatch_event
from app.orchestrator.policy import is_soft_closed, soft_close
from app.orchestrator.ports import Services, StorePort, TurnResult
from app.orchestrator.state import SessionStateStore, ThreadState

_DELIVERED_BLOCKS = frozenset(
    {"file_card", "data_card", "note_list_card", "ticket_confirmation"}
)
_COLLECTING_BLOCKS = frozenset({"stepper_card", "calendar"})
_LOOP_KINDS = frozenset({ChipActionKind.send_text, ChipActionKind.deep_link})


class Orchestrator:
    def __init__(
        self,
        *,
        services: Services,
        store: StorePort,
        llm: LLMClient,
        config: RemoteConfig,
        sessions: SessionStateStore | None = None,
    ) -> None:
        self.services = services
        self.store = store
        self.llm = llm
        self.config = config
        self.sessions = sessions or SessionStateStore()

    # -- public entrypoint ---------------------------------------------------

    def handle_turn(self, request: ChatRequest) -> ChatResponse:
        if request.thread_id is None:
            return self._bootstrap(request)

        state = self.sessions.get(request.thread_id)
        if state is None:
            state = self._new_state(request.session, request.thread_id)
            self.sessions.put(request.thread_id, state)

        with trace_manager.span(
            SpanType.agent,
            thread_id=state.thread_id,
            user_id=state.user_id,
            turn_number=state.turn_number + 1,
        ):
            return self._run_turn(request, state)

    # -- bootstrap -----------------------------------------------------------

    def _bootstrap(self, request: ChatRequest) -> ChatResponse:
        thread_id = str(uuid.uuid4())
        state = self._new_state(request.session, thread_id)
        self.sessions.put(thread_id, state)
        with trace_manager.span(
            SpanType.agent, thread_id=thread_id, user_id=state.user_id, turn_number=0
        ):
            return build_session_seed(request, self.config, thread_id=thread_id)

    def _new_state(self, session: SessionContext, thread_id: str) -> ThreadState:
        return ThreadState(
            thread_id=thread_id,
            user_id=session.user_id,
            session_id=session.session_id,
            access_token=session.access_token,
            platform=session.platform,
            page=session.page,
            is_dark_theme=session.is_dark_theme,
        )

    # -- turn pipeline -------------------------------------------------------

    def _run_turn(self, request: ChatRequest, state: ThreadState) -> ChatResponse:
        limits = self.config.limits
        state.turn_number += 1
        state.messages_used += 1
        context = state.to_context()
        user_message = self._user_message(request)

        if is_soft_closed(state, limits):
            turn = TurnResult(blocks=soft_close(state), escalated=True)
            return self._finalize(state, turn, user_message)

        if request.message is not None:
            turn = run_agentic_loop(
                llm=self.llm,
                services=self.services,
                text=request.message,
                state=state,
                context=context,
                limits=limits,
            )
        elif request.action is not None and request.action.kind in _LOOP_KINDS:
            turn = run_agentic_loop(
                llm=self.llm,
                services=self.services,
                text=str(request.action.payload.get("text", "")),
                state=state,
                context=context,
                limits=limits,
            )
        elif request.action is not None:
            turn = dispatch_event(request.action, state, self.services)
        else:
            turn = TurnResult(blocks=[Bubble(text="What can I get for you?")])

        return self._finalize(state, turn, user_message)

    # -- assembly + fan-out --------------------------------------------------

    def _finalize(
        self, state: ThreadState, turn: TurnResult, user_message: str | None
    ) -> ChatResponse:
        state.conversation_state = self._conversation_state(state, turn)
        turn_id = str(uuid.uuid4())

        record = TurnRecord(
            thread_id=state.thread_id,
            turn_id=turn_id,
            user_id=state.user_id,
            turn_number=state.turn_number,
            user_message=user_message,
            assistant_message=turn.assistant_text,
            intent=turn.intent,
            extracted_params=(
                turn.extracted_params.model_dump(mode="json") if turn.extracted_params else None
            ),
            tool_calls=turn.tool_calls,
            retrieval_context=turn.retrieval_context,
            render_blocks=[b.model_dump(by_alias=True, mode="json") for b in turn.blocks],
            model_version=self.llm.config.model,
        )
        # Non-blocking fan-out — the response never waits on the DB write.
        self.store.enqueue(record)

        state.history.append(TurnRef(turn_id=turn_id, turn_number=state.turn_number))
        self.sessions.put(state.thread_id, state)

        return ChatResponse(
            thread_id=state.thread_id,
            turn_number=state.turn_number,
            blocks=turn.blocks,
            intent=turn.intent,
            conversation_state=state.conversation_state,
            caps=Caps(
                messages_used=state.messages_used,
                messages_cap=self.config.limits.message_cap,
                follow_ups_used=state.follow_up_count,
            ),
            config_slice=None,
        )

    @staticmethod
    def _user_message(request: ChatRequest) -> str | None:
        if request.message is not None:
            return request.message
        if request.action is not None and request.action.kind in _LOOP_KINDS:
            return str(request.action.payload.get("text", "")) or None
        return None

    @staticmethod
    def _conversation_state(state: ThreadState, turn: TurnResult) -> ConversationState:
        if state.conversation_state is ConversationState.escalated or turn.escalated:
            return ConversationState.escalated
        types = {getattr(b, "type", None) for b in turn.blocks}
        if types & _DELIVERED_BLOCKS:
            return ConversationState.delivered
        if types & _COLLECTING_BLOCKS:
            return ConversationState.collecting
        if "error_bubble" in types:
            return ConversationState.error
        return ConversationState.delivered
