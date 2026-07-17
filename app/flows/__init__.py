"""Flow package + discovery registry (owned by flow-engine-runtime).

This file is GENERIC by design (proposal / decomposition-map line 47): adding a
report flow means dropping an ``app/flows/<name>.py`` that exposes a module-level
``FLOW`` — it NEVER requires an edit here. The registry is discovered lazily by
scanning this package for those modules and keying each by its ``Intent``.
"""

from __future__ import annotations

import sys

from app.contracts.flow import FlowSpec
from app.contracts.router import Intent
from app.engine.registry import FlowRegistry

_REGISTRY: FlowRegistry | None = None


def registry(*, refresh: bool = False) -> FlowRegistry:
    """The process-wide flow registry, discovered on first use. ``refresh=True``
    rescans (useful after a flow module is added at runtime / in tests)."""
    global _REGISTRY
    if _REGISTRY is None or refresh:
        reg = FlowRegistry()
        reg.discover(sys.modules[__name__])
        _REGISTRY = reg
    return _REGISTRY


def get_flow(intent: Intent) -> FlowSpec | None:
    """Look up the discovered flow for an intent (``None`` if none is registered)."""
    return registry().get(intent)


def register(flow: FlowSpec) -> None:
    """Programmatically register a flow (discovery is the primary path; this is for
    tests / dynamic registration)."""
    registry().register(flow)
