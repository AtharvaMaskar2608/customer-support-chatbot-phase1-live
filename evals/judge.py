"""Judge / simulated-user model wrapper (eval-harness capability).

`JiniJudgeLLM` wraps **`claude-opus-4-8`** as a DeepEval `DeepEvalBaseLLM`, used
both as the metric judge and as the `ConversationSimulator`'s simulated-user
model. It is deliberately a *different, stronger* model than the
`claude-sonnet-5` system-under-test: a judge that shares the SUT's model exhibits
self-preference bias. It reuses the existing `ANTHROPIC_API_KEY` — no new secret.

**Decision for review** (see proposal §Why): the documented alternative is
DeepEval's native OpenAI judge (`gpt-4.1`) via `OPENAI_API_KEY`, selectable with
`JINI_JUDGE_PROVIDER=openai`.

Construction is key-free and network-free: `load_model()` does NOT build an SDK
client, so the judge object (and any metric that holds it) can be constructed
offline in CI. The Anthropic client is built lazily on the first `generate`
call — the only place an `ANTHROPIC_API_KEY` is required.
"""

from __future__ import annotations

import json
import os
from typing import Any

from deepeval.models import DeepEvalBaseLLM

#: The proposed judge model — stronger than and independent of the SUT.
JUDGE_MODEL = "claude-opus-4-8"

#: The documented OpenAI alternative (DeepEval native string judge).
OPENAI_JUDGE_MODEL = "gpt-4.1"


def _extract_json(text: str) -> Any:
    """Best-effort parse of a JSON object/array out of an LLM text response.

    DeepEval metric prompts instruct the judge to emit JSON; models occasionally
    wrap it in prose or fences. Mirrors the native models' trim-and-load: take the
    outermost ``{...}`` / ``[...]`` span and parse it, falling back to the raw
    string so the DeepEval caller can run its own JSON repair.
    """
    stripped = text.strip()
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = stripped.find(open_ch)
        end = stripped.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(stripped)


class JiniJudgeLLM(DeepEvalBaseLLM):
    """`claude-opus-4-8` judge + simulated-user model for the Jini eval harness."""

    def __init__(self, model: str | None = None, max_tokens: int = 4096) -> None:
        self._model_id = model or JUDGE_MODEL
        self._max_tokens = max_tokens
        self._sync_client: Any = None
        self._async_client: Any = None
        # super().__init__ sets self.name and calls load_model() (see below).
        super().__init__(self._model_id)

    def load_model(self) -> None:
        """Lazy by design: build no SDK client here so the judge constructs with
        no API key and no network (CI-safe). The client is created on first use."""
        return None

    def get_model_name(self) -> str:
        return self._model_id

    # -- lazy Anthropic clients (the only place a key is required) --------------

    def _client(self) -> Any:
        if self._sync_client is None:
            from anthropic import Anthropic

            self._sync_client = Anthropic()
        return self._sync_client

    def _aclient(self) -> Any:
        if self._async_client is None:
            from anthropic import AsyncAnthropic

            self._async_client = AsyncAnthropic()
        return self._async_client

    @staticmethod
    def _content(prompt: Any) -> Any:
        # Anthropic accepts a plain string or a content-block list; pass through.
        return prompt

    @staticmethod
    def _text(message: Any) -> str:
        return "".join(
            getattr(b, "text", "")
            for b in getattr(message, "content", []) or []
            if getattr(b, "type", None) == "text"
        )

    # -- DeepEvalBaseLLM interface ---------------------------------------------
    # generate_with_schema / a_generate_with_schema (called by metrics) delegate
    # to these via the base class, passing schema=<pydantic model>.

    def generate(self, prompt: Any, schema: Any = None) -> Any:
        message = self._client().messages.create(
            model=self._model_id,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": self._content(prompt)}],
        )
        text = self._text(message)
        if schema is None:
            return text
        return schema.model_validate(_extract_json(text))

    async def a_generate(self, prompt: Any, schema: Any = None) -> Any:
        message = await self._aclient().messages.create(
            model=self._model_id,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": self._content(prompt)}],
        )
        text = self._text(message)
        if schema is None:
            return text
        return schema.model_validate(_extract_json(text))


def build_judge(provider: str | None = None) -> Any:
    """Return the selected judge model for metrics and the simulator.

    - ``anthropic`` (default): the `claude-opus-4-8` `JiniJudgeLLM` wrapper.
    - ``openai``: the string ``"gpt-4.1"`` so DeepEval uses its native OpenAI
      judge via the existing `OPENAI_API_KEY`.

    Selection order: explicit ``provider`` arg, else ``JINI_JUDGE_PROVIDER`` env,
    else ``anthropic``. A metric accepts ``Union[str, DeepEvalBaseLLM]``, so both
    return types are valid `model=` arguments.
    """
    choice = (provider or os.getenv("JINI_JUDGE_PROVIDER") or "anthropic").lower()
    if choice in ("anthropic", "claude", "opus"):
        return JiniJudgeLLM()
    if choice in ("openai", "gpt"):
        return os.getenv("JINI_OPENAI_JUDGE_MODEL", OPENAI_JUDGE_MODEL)
    raise ValueError(
        f"Unknown JINI_JUDGE_PROVIDER {choice!r}; expected 'anthropic' or 'openai'."
    )
