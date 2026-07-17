"""tracing-observability capability — concrete DeepEval wiring.

The implementation of the frozen ``tracing-conventions`` contract
(``app/contracts/tracing.py``): the global setup wrapper, the PII mask, typed
span helpers + thread stitching, the dual Anthropic auto-patch / manual
llm-span path, trace housekeeping, and the production no-local-judge guard.

Other packages import from here so span typing and PII redaction are wired
identically everywhere, rather than each re-deriving decorator usage.
"""

from __future__ import annotations

from app.tracing.mask import mask_pii

__all__ = [
    "mask_pii",
]
