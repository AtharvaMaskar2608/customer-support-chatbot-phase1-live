"""LLM client wrapper (llm-client capability, design D9/D15).

A thin wrapper over the ``anthropic`` SDK with the owner-pinned model IDs. It
selects the model from config, exposes a single completion method, and passes
``tools=`` / ``tool_choice=`` / ``output_config`` through unchanged (native tool
use + structured non-tool outputs). It contains NO prompt, routing, or flow logic.

Because ``claude-sonnet-5`` runs adaptive thinking by default and rejects
non-default sampling params, the wrapper never exposes or sends
``temperature`` / ``top_p`` / ``top_k``, omits the ``thinking`` parameter
(adaptive by default), and defaults ``max_tokens`` to ~16000 for non-streaming
calls. Structured decisions arrive only as schema-validated ``tool_use`` blocks or
``output_config.format`` json_schema output — never parsed from free-text JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.contracts.tracing import SpanType

#: Owner-pinned model IDs (spec §2.1; these replace the flow spec's non-existent
#: "sonnet-4-6"). The router/RAG generation uses the pinned pair; the DeepEval
#: judge model (claude-opus-4-8) is separate and not configured here.
DEFAULT_MODEL = "claude-sonnet-5"
CHEAP_MODEL = "claude-haiku-4-5-20251001"

#: ~16000-token non-streaming default (design D9).
DEFAULT_MAX_TOKENS = 16000


@dataclass
class LLMConfig:
    """Backend-configurable model selection. ``cheap_model_toggle`` swaps the
    default Sonnet for the Haiku toggle; the active model is selected from config,
    not hardcoded at the call site."""

    model: str = DEFAULT_MODEL
    cheap_model_toggle: bool = False
    max_tokens: int = DEFAULT_MAX_TOKENS


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class LLMResponse:
    """The wrapper's return: response text + token usage + stop_reason + the raw
    content blocks (incl. any ``tool_use`` blocks) so the orchestrator can drive
    the agentic loop."""

    text: str
    usage: Usage
    stop_reason: str | None
    content: list[Any] = field(default_factory=list)
    tool_use: list[Any] = field(default_factory=list)

    @classmethod
    def from_anthropic(cls, message: Any) -> "LLMResponse":
        content = list(getattr(message, "content", []) or [])
        text = "".join(getattr(b, "text", "") for b in content if getattr(b, "type", None) == "text")
        tool_use = [b for b in content if getattr(b, "type", None) == "tool_use"]
        usage = getattr(message, "usage", None)
        return cls(
            text=text,
            usage=Usage(
                prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage, "output_tokens", 0) or 0,
            ),
            stop_reason=getattr(message, "stop_reason", None),
            content=content,
            tool_use=tool_use,
        )


class LLMClient:
    """Pinned-model Claude client wrapper. The Anthropic client is constructed
    lazily so the wrapper can be built (and its request kwargs inspected) with no
    API key and no network."""

    #: The tracing span every model call is recorded on.
    span_type = SpanType.llm

    def __init__(self, config: LLMConfig | None = None, client: Any = None) -> None:
        self.config = config or LLMConfig()
        self._client = client

    def _resolve_model(self, model: str | None) -> str:
        if model is not None:
            return model
        return CHEAP_MODEL if self.config.cheap_model_toggle else self.config.model

    def build_request(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[Any] | None = None,
        tool_choice: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Build the Anthropic request kwargs. Never includes temperature/top_p/
        top_k or thinking; passes tools/tool_choice/output_config through unchanged."""
        request: dict[str, Any] = {
            "model": self._resolve_model(model),
            "max_tokens": max_tokens or self.config.max_tokens,
            "messages": messages,
        }
        if system is not None:
            request["system"] = system
        if tools is not None:
            request["tools"] = tools
        if tool_choice is not None:
            request["tool_choice"] = tool_choice
        if output_config is not None:
            request["output_config"] = output_config
        return request

    def _anthropic(self) -> Any:
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic()
        return self._client

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[Any] | None = None,
        tool_choice: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Issue one non-streaming completion and return text + usage + stop_reason.
        The call is recorded on the ``llm`` tracing span."""
        request = self.build_request(
            messages=messages,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            output_config=output_config,
            max_tokens=max_tokens,
            model=model,
        )
        message = self._anthropic().messages.create(**request)
        return LLMResponse.from_anthropic(message)
