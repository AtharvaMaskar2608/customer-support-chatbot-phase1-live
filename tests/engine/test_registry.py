"""T9: discovery registry (proposal §Flow discovery-registry).

The key spec claim: a flow is discovered from a module-level FLOW with NO edit to
app/flows/__init__.py.
"""

from __future__ import annotations

import importlib
import sys
import textwrap

from app.contracts.flow import FlowSpec
from app.contracts.router import Intent

import app.flows as flows
from app.engine.registry import FlowRegistry, discover

_FLOW_MODULE = textwrap.dedent(
    """
    from datetime import date
    from app.contracts.flow import DateWindow, FlowConfig, Step, StepKind
    from app.contracts.router import Intent

    class _PnlFlow:
        intent = Intent.report_pnl
        config = FlowConfig(intent=Intent.report_pnl, window=DateWindow(floor=date(2018, 1, 1), cap_relative_days=0, max_range_years=2))
        def steps(self):
            return [Step(id="segment", kind=StepKind.segment)]

    FLOW = _PnlFlow()
    """
)


def _temp_flow_package(tmp_path, name: str):
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "pnl.py").write_text(_FLOW_MODULE)
    sys.path.insert(0, str(tmp_path))
    return importlib.import_module(name)


def test_discovers_module_level_flow_without_editing_init(tmp_path):
    package = _temp_flow_package(tmp_path, "fakeflows_disc")
    try:
        found = discover(package)
        assert Intent.report_pnl in found
        flow = found[Intent.report_pnl]
        assert flow.intent is Intent.report_pnl
        assert isinstance(flow, FlowSpec)  # satisfies the frozen runtime_checkable protocol
    finally:
        sys.path.remove(str(tmp_path))
        for mod in [m for m in sys.modules if m.startswith("fakeflows_disc")]:
            del sys.modules[mod]


def test_registry_register_and_get_roundtrip(tmp_path):
    package = _temp_flow_package(tmp_path, "fakeflows_reg")
    try:
        flow = discover(package)[Intent.report_pnl]
        reg = FlowRegistry()
        assert reg.get(Intent.report_pnl) is None
        reg.register(flow)
        assert reg.get(Intent.report_pnl) is flow
        assert reg.intents() == {Intent.report_pnl}
    finally:
        sys.path.remove(str(tmp_path))
        for mod in [m for m in sys.modules if m.startswith("fakeflows_reg")]:
            del sys.modules[mod]


def test_app_flows_registry_is_generic_discovery_over_the_package():
    # The app/flows registry is populated PURELY by discovery: dropping an
    # app/flows/<name>.py with a module-level FLOW registers it with no edit to
    # __init__.py. So registry() must mirror discover() over the real package,
    # whatever flow modules have shipped to main — the genericity guarantee, not a
    # hand-maintained list. (An intent whose module is absent stays unregistered.)
    reg = flows.registry(refresh=True)
    assert isinstance(reg, FlowRegistry)
    expected = discover(flows)
    assert reg.intents() == set(expected)
    for intent in expected:
        assert flows.get_flow(intent) is not None
