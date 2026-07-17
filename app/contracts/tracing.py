"""Tracing conventions (tracing-conventions capability).

Span taxonomy (agent/retriever/llm/tool matching DeepEval's ``@observe(type=...)``),
the ``trace_manager.configure(...)`` setup contract, the PII ``mask`` hook signature
+ a default redactor, and thread-based multi-turn stitching. Confident AI export is
optional — tracing works fully offline. The actual instrumentation lives in the
tracing change; this module defines the contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Mapping


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


def default_mask(data: Any) -> Any:
    """Recursively redact PII-keyed values in trace data. Redacts names, emails,
    Client IDs, and ledger amounts (and session credentials / sensitive handles).
    The get-profile full response must never be traced — only the extracted first
    name is retained in memory for the greeting."""
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
    return data


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
    """Holds the active tracing configuration. ``configure`` accepts the documented
    parameters and functions without a Confident AI key."""

    def __init__(self) -> None:
        self.config: TraceConfig | None = None

    def configure(
        self,
        *,
        openai_client: Any = None,
        confident_api_key: str | None = None,
        environment: Environment = "development",
        sampling_rate: float = 1.0,
        mask: MaskFn | None = None,
    ) -> TraceConfig:
        self.config = TraceConfig(
            environment=environment,
            sampling_rate=sampling_rate,
            confident_api_key=confident_api_key,
            openai_client=openai_client,
            mask=mask or default_mask,
            export_enabled=confident_api_key is not None,
        )
        return self.config


#: The process-wide tracing manager.
trace_manager = TraceManager()
