"""Flow discovery registry (proposal §Flow discovery-registry).

Discovery-based so adding a flow needs NO edit to any shared file: each flow change
ships ``app/flows/<name>.py`` exposing a module-level ``FLOW`` (the frozen
``FLOW_ATTR``) satisfying the frozen ``FlowSpec``; the engine imports/scans the flow
package and keys each ``FLOW`` by its ``Intent``. There is no register decorator and
no hand-maintained registry list.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from app.contracts.flow import FLOW_ATTR, FlowSpec
from app.contracts.router import Intent


def discover(package: ModuleType) -> dict[Intent, FlowSpec]:
    """Scan ``package``'s submodules for a module-level ``FLOW`` that satisfies the
    frozen ``FlowSpec`` and return ``{intent: FLOW}``. Modules without a valid
    ``FLOW`` are skipped."""
    found: dict[Intent, FlowSpec] = {}
    for info in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
        module = importlib.import_module(info.name)
        flow = getattr(module, FLOW_ATTR, None)
        if flow is not None and isinstance(flow, FlowSpec):
            found[flow.intent] = flow
    return found


class FlowRegistry:
    """An ``Intent → FlowSpec`` lookup, populated by ``discover`` and/or ``register``."""

    def __init__(self) -> None:
        self._by_intent: dict[Intent, FlowSpec] = {}

    def register(self, flow: FlowSpec) -> None:
        """Register (or replace) a flow, keyed by its intent."""
        self._by_intent[flow.intent] = flow

    def register_all(self, flows: dict[Intent, FlowSpec]) -> None:
        self._by_intent.update(flows)

    def discover(self, package: ModuleType) -> None:
        """Populate from an importlib scan of ``package``'s flow modules."""
        self.register_all(discover(package))

    def get(self, intent: Intent) -> FlowSpec | None:
        return self._by_intent.get(intent)

    def intents(self) -> set[Intent]:
        return set(self._by_intent)
