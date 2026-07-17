"""Tracing conventions (tracing-conventions capability).

Span taxonomy (agent/retriever/llm/tool matching DeepEval's ``@observe(type=...)``),
the ``trace_manager.configure(...)`` setup contract, the PII ``mask`` hook signature
+ a default redactor, and thread-based multi-turn stitching. Confident AI export is
optional — tracing works fully offline. The actual instrumentation lives in the
tracing change; this module defines the contract.
"""

from __future__ import annotations

import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, Literal, Mapping


class SpanType(str, Enum):
    """The four typed spans. The canonical shape is a root ``agent`` span wrapping
    a ``retriever`` span and an ``llm`` span, with ``tool`` spans for FinX/Freshdesk
    calls."""

    agent = "agent"
    retriever = "retriever"
    llm = "llm"
    tool = "tool"


Environment = Literal["development", "staging", "production"]

#: A PII-redaction hook applied to trace data before any export.
MaskFn = Callable[[Any], Any]

#: Keys whose values are PII and must be redacted (case-insensitive substring match):
#: names, emails, Client IDs, ledger amounts, and the session credentials.
PII_KEYS: frozenset[str] = frozenset(
    {
        "email",
        "name",
        "firstholdername",
        "pan",
        "mobile",
        "client_id",
        "clientid",
        "invcode",
        "address",
        "debit",
        "credit",
        "amount",
        "ledger",
        "bank",
        "ifsc",
        "dob",
        "dateofbirth",
        "access_token",
        "accesstoken",
        "session_id",
        "sessionid",
        "cmllink",
        "file_id",
    }
)

_REDACTED = "***"

#: Redact email addresses embedded inside string values (e.g. the registered
#: email leaked, uppercased, inside a "PnL Report mail sent successfully to …"
#: confirmation string) — value-level, not just key-level.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def default_mask(data: Any) -> Any:
    """Recursively redact PII in trace data before export. Redacts PII-keyed
    values (names, emails, Client IDs, ledger amounts, session credentials /
    sensitive handles) AND email addresses embedded inside string values. The
    get-profile full response must never be traced — only the extracted first name
    is retained in memory for the greeting."""
    if isinstance(data, Mapping):
        masked: dict[Any, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and any(p in key.lower() for p in PII_KEYS):
                masked[key] = _REDACTED
            else:
                masked[key] = default_mask(value)
        return masked
    if isinstance(data, list):
        return [default_mask(item) for item in data]
    if isinstance(data, str):
        return _EMAIL_RE.sub(_REDACTED, data)
    return data


def new_thread_id() -> str:
    """A per-session ``thread_id`` (uuid4). Per-turn traces are stitched into one
    conversation by sharing this id (via DeepEval ``update_current_trace(...)``);
    conversation state is the app's responsibility — DeepEval only observes."""
    return str(uuid.uuid4())


def inline_judge_allowed(environment: Environment) -> bool:
    """Production rule: local LLM-judge metrics are NEVER run inline in production
    (they add blocking latency). Async ``metric_collection`` is used instead, and
    long-running servers periodically clear traces. Returns False in production."""
    return environment != "production"


@dataclass
class Span:
    """A typed tracing span. Retriever spans carry the per-turn
    ``retrieval_context`` (canonical ``list[str]`` from app/contracts/rag.py);
    llm spans carry the model id and token usage."""

    span_type: SpanType
    attributes: dict[str, Any] = field(default_factory=dict)

    def set(self, **attributes: Any) -> "Span":
        self.attributes.update(attributes)
        return self


@dataclass
class TraceConfig:
    """The result of ``configure(...)`` — captures the tracing setup. Confident AI
    export is enabled only when a key is supplied; tracing works offline otherwise."""

    environment: Environment = "development"
    sampling_rate: float = 1.0
    confident_api_key: str | None = None
    openai_client: Any = None
    mask: MaskFn = field(default=default_mask)
    export_enabled: bool = False


class TraceManager:
    """Holds the active tracing configuration and opens typed spans. ``configure``
    accepts the documented parameters and functions without a Confident AI key.

    NOTE: the installed DeepEval ``configure()`` signature documents only
    ``openai_client``; if the version lacks an Anthropic auto-patch hook, Claude
    calls SHALL be logged manually on the ``llm`` span (see LLMClient)."""

    def __init__(self) -> None:
        self.config: TraceConfig | None = None
        #: The most recently opened span (the real Confident-AI export is wired by
        #: the tracing change; offline this holds the span shape for inspection).
        self.last_span: Span | None = None

    def configure(
        self,
        *,
        openai_client: Any = None,
        confident_api_key: str | None = None,
        environment: Environment = "development",
        sampling_rate: float = 1.0,
        mask: MaskFn | None = None,
    ) -> TraceConfig:
        """Set up tracing. ``confident_api_key`` is optional — tracing works fully
        offline without it. The installed DeepEval ``configure()`` documents only
        ``openai_client``; the remaining params (environment, sampling_rate, mask)
        are this contract's superset applied by the tracing change."""
        self.config = TraceConfig(
            environment=environment,
            sampling_rate=sampling_rate,
            confident_api_key=confident_api_key,
            openai_client=openai_client,
            mask=mask or default_mask,
            export_enabled=confident_api_key is not None,
        )
        return self.config

    @contextmanager
    def span(self, span_type: SpanType, **attributes: Any) -> Iterator[Span]:
        """Open a typed span. Every observed span sets its ``type``. The canonical
        shape is a root ``agent`` span wrapping a ``retriever`` and an ``llm`` span,
        with ``tool`` spans for FinX/Freshdesk calls."""
        current = Span(span_type=span_type, attributes=dict(attributes))
        try:
            yield current
        finally:
            self.last_span = current


#: The process-wide tracing manager.
trace_manager = TraceManager()
