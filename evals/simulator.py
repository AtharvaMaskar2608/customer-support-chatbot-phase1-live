"""ConversationSimulator plumbing (eval-harness capability).

The spec calls this *required plumbing, not optional* (§7.6): it is what unlocks
the turn-level RAG and tool metrics. The DeepEval `ConversationSimulator`
role-plays the user (via the judge model) and, on every assistant turn, invokes
`model_callback`, which drives the real Jini app and returns a **rich `Turn`**:

    Turn(role="assistant",
         content=<concatenated bot bubbles>,
         retrieval_context=<qa_chunks text from rag-service>,
         tools_called=<flow + raise_ticket/get_ticket_status calls>)

`content`, `retrieval_context`, and `tools_called` must be populated on every
assistant turn or the `TurnFaithfulness`/`TurnContextual*` and
`ToolUse`/`GoalAccuracy` metrics have no data.

Wave-1 note: the mapping is authored and unit-tested OFFLINE against fakes. The
live *source* of `retrieval_context` / `tools_called` is a server-side eval
channel (retriever spans / tool trace), which is NOT on the client wire contract
(`ChatResponse` deliberately omits both). The `HttpJiniDriver` takes that channel
as an injected dependency; Wave 2 wires it against the assembled app. Until then
`get_default_driver()` refuses to run live, so nothing here makes a live call in
CI.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from deepeval.simulator import ConversationSimulator
from deepeval.test_case import Turn, ToolCall

from app.contracts.wire import ChatRequest, ChatResponse, SessionContext

#: Jini's standing greeting, used to seed each simulated conversation.
DEFAULT_GREETING = "Hi, I'm Jini — your Choice support assistant. How can I help?"

#: Render-block type -> the field carrying its user-visible bot text. Only bot
#: bubbles contribute to `content`; `user_bubble` (the echoed user turn) and
#: non-text cards (chips, steppers, calendars, file/data cards) are excluded.
_TEXT_BLOCK_FIELDS: dict[str, str] = {
    "bubble": "text",
    "error_bubble": "text",
    "ticket_confirmation": "message",
}


# ---------------------------------------------------------------------------
# Rich result types (the app-side shape the callback maps into a DeepEval Turn)
# ---------------------------------------------------------------------------


@dataclass
class JiniToolCall:
    """One flow/ticket tool call captured on an assistant turn."""

    name: str
    description: str = ""
    input_parameters: dict[str, Any] = field(default_factory=dict)
    output: Any = None


@dataclass
class JiniChatResult:
    """A single Jini turn's rich result: bot text + retrieval context + tools."""

    text: str
    retrieved_chunks: list[str] = field(default_factory=list)
    tool_calls: list[JiniToolCall] = field(default_factory=list)
    thread_id: str | None = None


# ---------------------------------------------------------------------------
# Pure mapping (unit-tested offline; no network)
# ---------------------------------------------------------------------------


def _block_type(block: Any) -> str | None:
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)


def _block_field(block: Any, name: str) -> Any:
    return block.get(name) if isinstance(block, dict) else getattr(block, name, None)


def render_blocks_to_text(blocks: list[Any]) -> str:
    """Concatenate the bot bubbles from a render-block array into one string.

    Accepts either wire-model render blocks or their JSON dicts. Non-text blocks
    (chips, cards, calendars, the echoed user bubble) are skipped.
    """
    parts: list[str] = []
    for block in blocks:
        field_name = _TEXT_BLOCK_FIELDS.get(_block_type(block) or "")
        if not field_name:
            continue
        value = _block_field(block, field_name)
        if value:
            parts.append(str(value))
    return "\n\n".join(parts)


def map_chat_response(
    response: ChatResponse | dict[str, Any],
    *,
    retrieval_context: list[str] | None = None,
    tool_calls: list[JiniToolCall] | None = None,
) -> JiniChatResult:
    """Map a `/api/chat` response + eval-channel signals into a `JiniChatResult`."""
    if isinstance(response, dict):
        response = ChatResponse.model_validate(response)
    return JiniChatResult(
        text=render_blocks_to_text(response.blocks),
        retrieved_chunks=list(retrieval_context or []),
        tool_calls=list(tool_calls or []),
        thread_id=response.thread_id,
    )


def to_turn(result: JiniChatResult) -> Turn:
    """Map a rich `JiniChatResult` into a DeepEval assistant `Turn`.

    `retrieval_context` and `tools_called` are set to None when empty so the
    metrics that require them skip cleanly rather than scoring against [].
    """
    tools = [
        ToolCall(
            name=tc.name,
            description=tc.description or None,
            input_parameters=tc.input_parameters or None,
            output=tc.output,
        )
        for tc in result.tool_calls
    ] or None
    return Turn(
        role="assistant",
        content=result.text,
        retrieval_context=result.retrieved_chunks or None,
        tools_called=tools,
    )


def greeting_seed_turn(greeting: str | None = None) -> Turn:
    """Jini's standing greeting as an assistant `Turn` to seed a conversation."""
    return Turn(role="assistant", content=greeting or DEFAULT_GREETING)


def eval_session(
    user_id: str = "EVAL0001",
    *,
    platform: str = "eval-harness",
    page: str = "support",
) -> SessionContext:
    """A synthetic session for driving the app in the harness.

    `session_id`/`access_token` are placeholders here; Wave 2 substitutes a real
    test client's SSO token so `AuthToken`-propagation goldens (G5) exercise the
    live auth path.
    """
    return SessionContext.from_url_params(
        userId=user_id,
        sessionId=f"eval-{uuid.uuid4()}",
        accessToken="eval-placeholder-token",
        platform=platform,
        page=page,
    )


# ---------------------------------------------------------------------------
# Drivers (the app-integration seam)
# ---------------------------------------------------------------------------


class JiniDriver(Protocol):
    """An async callable that drives one Jini turn and returns a rich result."""

    async def __call__(
        self, user_input: str, turns: list[Turn], thread_id: str
    ) -> JiniChatResult: ...


#: Signature of the server-side eval channel that supplies the retrieval context
#: and tool calls for a turn (not on the client wire contract). Wave 2 wires it.
EvalSignals = Callable[[str, int], Awaitable[tuple[list[str], list[JiniToolCall]]]]

#: Signature of the chat transport: POST /api/chat body -> response body.
PostChat = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class HttpJiniDriver:
    """Live driver: POST /api/chat, then enrich with the eval-signals channel.

    Both the transport (`post_chat`) and the retrieval/tool channel
    (`eval_signals`) are injected so this is testable offline and neutral about
    how Wave 2 reaches the app (httpx ASGI transport, real server, etc.).
    """

    def __init__(
        self,
        post_chat: PostChat,
        *,
        eval_signals: EvalSignals | None = None,
        session: SessionContext | None = None,
    ) -> None:
        self._post_chat = post_chat
        self._eval_signals = eval_signals
        self._session = session or eval_session()

    def _build_request(
        self, user_input: str, thread_id: str, turn_number: int
    ) -> dict[str, Any]:
        request = ChatRequest(
            session=self._session,
            message=user_input,
            thread_id=thread_id or None,
            turn_number=turn_number,
        )
        body = request.model_dump(by_alias=True, mode="json")
        # session_id / access_token are Field(exclude=True) so they never leak
        # back to the widget in RESPONSES, but the REQUEST must carry them for the
        # server to build the session. Inject them into the outgoing body (they
        # are declared fields, so the server accepts them on input).
        body["session"]["session_id"] = self._session.session_id
        body["session"]["access_token"] = self._session.access_token
        return body

    async def __call__(
        self, user_input: str, turns: list[Turn], thread_id: str
    ) -> JiniChatResult:
        turn_number = len(turns)
        raw = await self._post_chat(
            self._build_request(user_input, thread_id, turn_number)
        )
        response = ChatResponse.model_validate(raw)
        retrieval: list[str] = []
        tools: list[JiniToolCall] = []
        if self._eval_signals is not None:
            retrieval, tools = await self._eval_signals(
                response.thread_id, response.turn_number
            )
        return map_chat_response(
            response, retrieval_context=retrieval, tool_calls=tools
        )


_DEFAULT_DRIVER: JiniDriver | None = None


def set_default_driver(driver: JiniDriver | None) -> None:
    """Configure the driver `model_callback` uses (Wave 2 sets the live one)."""
    global _DEFAULT_DRIVER
    _DEFAULT_DRIVER = driver


def get_default_driver() -> JiniDriver:
    if _DEFAULT_DRIVER is None:
        raise RuntimeError(
            "No Jini driver configured. Wave-1 authors and unit-tests the callback "
            "mapping offline; set a driver via set_default_driver() (e.g. an "
            "HttpJiniDriver against the assembled app) before running live in Wave 2."
        )
    return _DEFAULT_DRIVER


# ---------------------------------------------------------------------------
# Callback + simulator wiring
# ---------------------------------------------------------------------------


async def drive_jini_chat(
    user_input: str,
    turns: list[Turn],
    thread_id: str,
    *,
    driver: JiniDriver | None = None,
) -> JiniChatResult:
    """Drive one Jini turn through the configured (or injected) driver."""
    return await (driver or get_default_driver())(user_input, turns, thread_id)


def make_model_callback(
    driver: JiniDriver | None = None,
) -> Callable[[str, list[Turn], str], Awaitable[Turn]]:
    """Build the async `model_callback` DeepEval invokes for each assistant turn."""

    async def model_callback(
        user_input: str, turns: list[Turn], thread_id: str
    ) -> Turn:
        result = await drive_jini_chat(user_input, turns, thread_id, driver=driver)
        return to_turn(result)

    return model_callback


async def model_callback(user_input: str, turns: list[Turn], thread_id: str) -> Turn:
    """Module-level callback matching the proposal contract; uses the default
    driver. See `make_model_callback` to bind a specific driver (e.g. in tests)."""
    result = await drive_jini_chat(user_input, turns, thread_id)
    return to_turn(result)


def build_simulator(
    judge: Any = None,
    *,
    driver: JiniDriver | None = None,
) -> ConversationSimulator:
    """Construct the `ConversationSimulator` with the Jini callback + judge model.

    `judge` defaults to the `claude-opus-4-8` wrapper; it plays the simulated
    user. `driver` (or the configured default) drives the real app.
    """
    if judge is None:
        from evals.judge import build_judge

        judge = build_judge()
    return ConversationSimulator(
        model_callback=make_model_callback(driver),
        simulator_model=judge,
    )
