"""Global tracing setup, Anthropic auto-patch path selection, housekeeping, and
the production no-local-judge guard (tracing-observability capability, §6.2/§6.5).

``configure_tracing`` is the one-time setup wrapper the orchestrator calls from
its FastAPI lifespan (this change exposes it; it does not edit ``app/main.py``).
It wraps DeepEval's ``trace_manager.configure(...)`` and always installs
``mask_pii`` so no PII leaves the process.

**Anthropic auto-patch — both paths, §6.2.** The documented DeepEval
``configure()`` historically exposed only ``openai_client=``. We probe the
*installed* signature at runtime:

- **Path A (auto):** ``configure()`` accepts ``anthropic_client`` → forward the
  pinned Claude client and let DeepEval intercept ``messages.create`` (model +
  token usage captured automatically).
- **Path B (manual):** only ``openai_client`` is exposed → configure without a
  client and log Claude calls manually via ``log_llm_span`` on the ``llm`` span.

The active path is logged at startup so it is never ambiguous which one is live.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from deepeval.tracing import trace_manager

from app.contracts.tracing import Environment, inline_judge_allowed
from app.tracing.mask import mask_pii

logger = logging.getLogger("app.tracing")

#: Dev traces every request; production samples a lower fraction (§6.2). No
#: tracing sampling field exists in the frozen remote-config, so this is the
#: default a caller may override by passing ``sampling_rate=`` explicitly.
DEFAULT_PROD_SAMPLING_RATE = 0.1

#: Anthropic auto-patch path resolved by the last ``configure_tracing`` call.
#: "A" = auto-patch (client forwarded to DeepEval); "B" = manual llm-span.
AUTO_PATCH = "A"
MANUAL_LLM_SPAN = "B"


class LocalMetricsInProductionError(RuntimeError):
    """Raised when local LLM-judge ``metrics=[...]`` are attached in production.

    Local judges add blocking latency; production must use async
    ``metric_collection=`` instead (§6.5)."""


def _supports_anthropic_autopatch() -> bool:
    """True when the installed DeepEval ``configure()`` exposes an
    ``anthropic_client`` parameter (Path A). Probed on the live callable so a
    monkeypatched/older ``configure`` resolves the path correctly."""
    try:
        params = inspect.signature(trace_manager.configure).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False
    return "anthropic_client" in params


def _default_sampling_rate(environment: Environment) -> float:
    return DEFAULT_PROD_SAMPLING_RATE if environment == "production" else 1.0


def configure_tracing(
    environment: Environment,
    sampling_rate: float | None = None,
    confident_api_key: str | None = None,
    *,
    anthropic_client: Any = None,
) -> None:
    """Configure DeepEval tracing once at startup (§6.2).

    - Defaults ``sampling_rate`` to ``1.0`` in development/staging and the lower
      ``DEFAULT_PROD_SAMPLING_RATE`` in production; an explicit value wins.
    - Always installs ``mask=mask_pii`` and tags the ``environment``.
    - Selects the Anthropic auto-patch path (A/B) by probing the installed
      ``configure()`` signature and logs which path is live.
    - Idempotent: safe to call once at startup (re-calling re-applies the same
      configuration).

    ``anthropic_client`` is the pinned Claude client wired for Path A
    auto-patching; it is a backward-compatible keyword-only superset of the
    documented ``(environment, sampling_rate, confident_api_key)`` contract and
    is ignored on Path B.
    """
    rate = sampling_rate if sampling_rate is not None else _default_sampling_rate(environment)

    kwargs: dict[str, Any] = {
        "environment": environment,
        "sampling_rate": rate,
        "mask": mask_pii,
        "confident_api_key": confident_api_key,
    }

    if _supports_anthropic_autopatch():
        active_path = AUTO_PATCH
        if anthropic_client is not None:
            kwargs["anthropic_client"] = anthropic_client
    else:
        active_path = MANUAL_LLM_SPAN

    trace_manager.configure(**kwargs)

    if active_path == AUTO_PATCH:
        logger.info(
            "DeepEval tracing configured: env=%s sampling_rate=%s "
            "Anthropic path=A (auto-patch; messages.create intercepted, "
            "client %s)",
            environment,
            rate,
            "wired" if anthropic_client is not None else "not supplied",
        )
    else:
        logger.info(
            "DeepEval tracing configured: env=%s sampling_rate=%s "
            "Anthropic path=B (manual llm-span; installed DeepEval configure() "
            "exposes no anthropic_client hook — use log_llm_span)",
            environment,
            rate,
        )


def active_anthropic_path() -> str:
    """The Anthropic auto-patch path the *installed* DeepEval resolves to:
    ``AUTO_PATCH`` ("A") or ``MANUAL_LLM_SPAN`` ("B"). Consumers use this to
    decide whether to call ``log_llm_span`` manually."""
    return AUTO_PATCH if _supports_anthropic_autopatch() else MANUAL_LLM_SPAN


def maybe_clear_traces() -> None:
    """Bound in-memory trace growth on the long-running server (§6.5).

    Clears buffered traces when tracing is **not** exporting to Confident AI
    (offline — nothing else drains the buffer). When a Confident AI key is
    configured, exports are flushed by DeepEval's background worker, so this is
    a no-op to avoid dropping not-yet-exported traces.
    """
    if getattr(trace_manager, "confident_api_key", None):
        return
    trace_manager.clear_traces()


def assert_no_local_metrics(environment: Environment, metrics: Any = None) -> None:
    """Refuse local LLM-judge ``metrics=[...]`` in production (§6.5).

    Local judges block the request with LLM-judge latency; production must route
    evaluation through async ``metric_collection=`` instead. Raises
    ``LocalMetricsInProductionError`` when ``environment == "production"`` and
    local ``metrics`` are present; a no-op otherwise (including empty metrics).
    Reuses the frozen ``inline_judge_allowed`` policy so the rule never drifts.
    """
    if metrics and not inline_judge_allowed(environment):
        raise LocalMetricsInProductionError(
            "Local LLM-judge metrics=[...] are not allowed in production "
            "(blocking latency); use async metric_collection= instead (§6.5)."
        )
