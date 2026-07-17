"""llm-client spec tests.

Asserts the pinned model IDs, model selection from config, no sampling params /
no thinking in the request, native tool-use passthrough (tools/tool_choice/
output_config unchanged), and the response mapping (text + usage + stop_reason +
tool_use). No network calls — build_request is pure and from_anthropic parses a
fake message.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.contracts.tracing import SpanType
from app.llm.client import (
    CHEAP_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    LLMClient,
    LLMConfig,
    LLMResponse,
)


def test_pinned_models():
    assert DEFAULT_MODEL == "claude-sonnet-5"
    assert CHEAP_MODEL == "claude-haiku-4-5-20251001"
    assert DEFAULT_MAX_TOKENS == 16000

    # Default: Sonnet.
    client = LLMClient()
    req = client.build_request(messages=[{"role": "user", "content": "hi"}])
    assert req["model"] == "claude-sonnet-5"
    assert req["max_tokens"] == 16000

    # Cheap-model toggle from config → Haiku.
    toggled = LLMClient(LLMConfig(cheap_model_toggle=True))
    assert toggled.build_request(messages=[])["model"] == "claude-haiku-4-5-20251001"

    # Explicit override wins.
    assert client.build_request(messages=[], model="claude-opus-4-8")["model"] == "claude-opus-4-8"


def test_no_sampling_params_or_thinking():
    client = LLMClient()
    req = client.build_request(messages=[{"role": "user", "content": "hi"}], system="sys")
    for forbidden in ("temperature", "top_p", "top_k", "thinking"):
        assert forbidden not in req
    assert req["system"] == "sys"


def test_tool_passthrough():
    client = LLMClient()
    tools = [{"name": "route", "description": "d", "input_schema": {"type": "object"}, "strict": True}]
    tool_choice = {"type": "tool", "name": "route", "disable_parallel_tool_use": True}
    output_config = {"format": {"type": "json_schema", "schema": {"type": "object"}}}
    req = client.build_request(
        messages=[{"role": "user", "content": "classify"}],
        tools=tools,
        tool_choice=tool_choice,
        output_config=output_config,
    )
    # Passed through unchanged.
    assert req["tools"] is tools
    assert req["tool_choice"] is tool_choice
    assert req["output_config"] is output_config
    # Still no sampling params.
    assert "temperature" not in req


def test_response_maps_text_usage_stop_reason():
    # A fake Anthropic message with mixed content blocks.
    fake = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="hello "),
            SimpleNamespace(type="text", text="world"),
            SimpleNamespace(type="tool_use", name="route", id="tu_1", input={"intent": "report_pnl"}),
        ],
        usage=SimpleNamespace(input_tokens=42, output_tokens=7),
        stop_reason="tool_use",
    )
    resp = LLMResponse.from_anthropic(fake)
    assert resp.text == "hello world"
    assert resp.usage.prompt_tokens == 42
    assert resp.usage.completion_tokens == 7
    assert resp.stop_reason == "tool_use"
    assert len(resp.tool_use) == 1
    assert resp.tool_use[0].name == "route"


def test_llm_span_is_llm():
    assert LLMClient.span_type is SpanType.llm
