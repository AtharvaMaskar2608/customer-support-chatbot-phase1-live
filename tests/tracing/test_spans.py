"""Tests for the typed span helpers, thread stitching, and the manual llm-span.

Written from proposal.md §"Typed span ergonomics + thread stitching" and the
Path B contract. Offline: no Confident AI connection, no real LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass

from deepeval.tracing import (
    current_span_context,
    current_trace_context,
    observe,
    update_current_span,
    update_current_trace,
)

from app.contracts.tracing import SpanType
from app.tracing import (
    agent_span,
    llm_span,
    log_llm_span,
    retriever_span,
    stitch_thread,
    tool_span,
)
from app.tracing import observe as reexported_observe
from app.tracing import update_current_span as reexported_update_span
from app.tracing import update_current_trace as reexported_update_trace


# --- Typed span helpers bind the frozen taxonomy -----------------------------


def test_span_helpers_bind_the_frozen_span_types():
    assert agent_span.keywords["type"] == SpanType.agent.value
    assert retriever_span.keywords["type"] == SpanType.retriever.value
    assert llm_span.keywords["type"] == SpanType.llm.value
    assert tool_span.keywords["type"] == SpanType.tool.value
    # All four helpers wrap the same underlying DeepEval decorator.
    for helper in (agent_span, retriever_span, llm_span, tool_span):
        assert helper.func is observe


def test_decorated_functions_open_the_right_typed_span():
    seen = {}

    @retriever_span
    def retrieve(query):
        seen["retriever"] = type(current_span_context.get()).__name__
        update_current_span(retrieval_context=["chunk one", "chunk two"])
        return ["chunk one", "chunk two"]

    @llm_span
    def generate(query, ctx):
        seen["llm"] = type(current_span_context.get()).__name__
        return "answer"

    @tool_span
    def call_tool():
        seen["tool"] = type(current_span_context.get()).__name__
        return "tool-result"

    @agent_span
    def answer(query):
        seen["agent"] = type(current_span_context.get()).__name__
        ctx = retrieve(query)
        call_tool()
        return generate(query, ctx)

    assert answer("hi") == "answer"
    assert seen == {
        "agent": "AgentSpan",
        "retriever": "RetrieverSpan",
        "llm": "LlmSpan",
        "tool": "ToolSpan",
    }


def test_span_helpers_accept_the_parameterized_form():
    # Both @llm_span and @llm_span(...) must work (functools.partial over observe).
    @llm_span(metric_collection="prod-metrics")
    def generate():
        return type(current_span_context.get()).__name__

    assert generate() == "LlmSpan"


# --- Thread stitching (§6.4) -------------------------------------------------


def test_stitch_thread_sets_thread_id_user_id_and_metadata_on_trace():
    captured = {}

    @agent_span
    def turn(user_message):
        stitch_thread("session-123", "X008593", turn_number=3, model_version="v2.1")
        trace = current_trace_context.get()
        captured["thread_id"] = trace.thread_id
        captured["user_id"] = trace.user_id
        captured["metadata"] = trace.metadata
        captured["tags"] = trace.tags
        return "reply"

    turn("hello")
    assert captured["thread_id"] == "session-123"
    assert captured["user_id"] == "X008593"
    assert captured["metadata"]["turn_number"] == 3
    assert captured["metadata"]["model_version"] == "v2.1"
    assert "conversation" in captured["tags"]


# --- Manual llm-span (Path B) ------------------------------------------------


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _AnthropicResponse:
    usage: _Usage


def test_log_llm_span_records_model_and_token_usage():
    captured = {}

    @llm_span
    def generate():
        response = _AnthropicResponse(_Usage(input_tokens=312, output_tokens=89))
        log_llm_span(response, model="claude-sonnet-5")
        span = current_span_context.get()
        captured["model"] = span.model
        captured["input_token_count"] = span.input_token_count
        captured["output_token_count"] = span.output_token_count
        return "answer"

    generate()
    assert captured["model"] == "claude-sonnet-5"
    assert captured["input_token_count"] == 312
    assert captured["output_token_count"] == 89


def test_log_llm_span_tolerates_missing_usage():
    # A malformed/streamed response must never break the request path: the call
    # must not raise, and the model is still recorded. (DeepEval leaves the token
    # counts unset when they are absent/zero — there is nothing to record.)
    @llm_span
    def generate():
        log_llm_span(object(), model="claude-haiku-4-5-20251001")
        span = current_span_context.get()
        return (span.model, span.input_token_count, span.output_token_count)

    model, input_tokens, output_tokens = generate()
    assert model == "claude-haiku-4-5-20251001"
    assert input_tokens in (0, None)
    assert output_tokens in (0, None)


# --- Re-exports --------------------------------------------------------------


def test_reexports_are_the_deepeval_primitives():
    assert reexported_observe is observe
    assert reexported_update_span is update_current_span
    assert reexported_update_trace is update_current_trace
