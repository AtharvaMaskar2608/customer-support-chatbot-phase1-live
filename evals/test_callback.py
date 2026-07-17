"""Offline structural tests for the simulator callback (eval-harness capability).

Runs in CI with no app and no network. Proves the model_callback returns a RICH
assistant Turn (content + retrieval_context + tools_called) by driving it with a
fake driver, and checks the pure mapping helpers and the greeting seed. Part of
the `pytest evals/ -k "goldens or callback"` gate.
"""

from __future__ import annotations

import asyncio

import pytest

from deepeval.test_case import Turn
from evals.simulator import (
    DEFAULT_GREETING,
    JiniChatResult,
    JiniToolCall,
    get_default_driver,
    greeting_seed_turn,
    make_model_callback,
    model_callback,
    render_blocks_to_text,
    set_default_driver,
    to_turn,
)


class FakeDriver:
    """An async driver that returns a fixed rich result (no app, no network)."""

    def __init__(self, result: JiniChatResult) -> None:
        self._result = result
        self.calls: list[tuple[str, int, str]] = []

    async def __call__(self, user_input, turns, thread_id) -> JiniChatResult:
        self.calls.append((user_input, len(turns), thread_id))
        return self._result


@pytest.fixture
def reset_default_driver():
    """Isolate global driver state so tests don't leak into each other."""
    set_default_driver(None)
    yield
    set_default_driver(None)


def _rich_result() -> JiniChatResult:
    return JiniChatResult(
        text="Here is your P&L report.",
        retrieved_chunks=["chunk: P&L is under Reports", "chunk: export as PDF"],
        tool_calls=[
            JiniToolCall(
                name="get_pnl_report",
                description="Fetch the client's P&L",
                input_parameters={"period": "FY24"},
                output={"url": "https://x/pnl.pdf"},
            )
        ],
        thread_id="t-1",
    )


def test_render_blocks_to_text_concatenates_only_bot_bubbles():
    blocks = [
        {"type": "user_bubble", "text": "show my pnl"},          # echoed user turn — excluded
        {"type": "bubble", "text": "Here is your P&L report."},
        {"type": "chips", "items": ["FY24", "FY23"]},            # non-text card — excluded
        {"type": "ticket_confirmation", "message": "Ticket #42 raised."},
        {"type": "error_bubble", "text": "Could not fetch the older period."},
    ]
    text = render_blocks_to_text(blocks)
    assert text == (
        "Here is your P&L report.\n\n"
        "Ticket #42 raised.\n\n"
        "Could not fetch the older period."
    )


def test_to_turn_empty_signals_map_to_none():
    turn = to_turn(JiniChatResult(text="hello"))
    assert isinstance(turn, Turn)
    assert turn.role == "assistant"
    assert turn.content == "hello"
    assert turn.retrieval_context is None
    assert turn.tools_called is None


def test_to_turn_maps_rich_result():
    turn = to_turn(_rich_result())
    assert turn.content == "Here is your P&L report."
    assert turn.retrieval_context == ["chunk: P&L is under Reports", "chunk: export as PDF"]
    assert turn.tools_called is not None and len(turn.tools_called) == 1
    tc = turn.tools_called[0]
    assert tc.name == "get_pnl_report"
    assert tc.input_parameters == {"period": "FY24"}
    assert tc.output == {"url": "https://x/pnl.pdf"}


def test_make_model_callback_returns_rich_turn():
    fake = FakeDriver(_rich_result())
    callback = make_model_callback(fake)
    turn = asyncio.run(callback("show my pnl", [], "t-1"))
    assert isinstance(turn, Turn)
    assert turn.role == "assistant"
    assert turn.content == "Here is your P&L report."
    assert turn.retrieval_context and turn.tools_called  # rich on every turn
    assert fake.calls == [("show my pnl", 0, "t-1")]


def test_module_callback_uses_default_driver(reset_default_driver):
    fake = FakeDriver(_rich_result())
    set_default_driver(fake)
    turn = asyncio.run(model_callback("show my pnl", [], "t-9"))
    assert turn.content == "Here is your P&L report."
    assert turn.tools_called and turn.tools_called[0].name == "get_pnl_report"


def test_default_driver_guard_raises_when_unset(reset_default_driver):
    with pytest.raises(RuntimeError, match="No Jini driver configured"):
        get_default_driver()


def test_greeting_seed_turn_shape():
    default_turn = greeting_seed_turn()
    assert default_turn.role == "assistant"
    assert default_turn.content == DEFAULT_GREETING
    custom = greeting_seed_turn("Namaste! Main Jini hoon.")
    assert custom.content == "Namaste! Main Jini hoon."
