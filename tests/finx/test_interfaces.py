"""FinX interface spec tests (specs/finx-client §Per-backend adapter set).

Asserts the five per-backend adapter Protocols and the FinXClient facade exist,
are runtime-checkable Protocols, and that a stub implementing a backend's methods
satisfies its Protocol (implementations bind at runtime in the adapters change).
"""

from __future__ import annotations

from app.finx.envelopes import Outcome, ParsedEnvelope
from app.finx.interfaces import (
    ADAPTER_PROTOCOLS,
    DotNetMiddlewareAdapter,
    FinxOmneCotiAdapter,
    FinXClient,
    GoMiddlewareAdapter,
    MfProfileAdapter,
    MisReportsAdapter,
)


def test_five_adapters_defined():
    # Five per-backend adapter Protocols — NOT one generic wrapper.
    assert len(ADAPTER_PROTOCOLS) == 5
    assert set(ADAPTER_PROTOCOLS) == {
        DotNetMiddlewareAdapter,
        GoMiddlewareAdapter,
        MisReportsAdapter,
        MfProfileAdapter,
        FinxOmneCotiAdapter,
    }
    # The facade is a separate Protocol.
    assert FinXClient not in ADAPTER_PROTOCOLS


def test_mis_adapter_protocol_runtime_checkable():
    class StubMis:
        async def generate_report(self, req):  # matches MisReportsAdapter
            return ParsedEnvelope(outcome=Outcome.success)

    assert isinstance(StubMis(), MisReportsAdapter)

    class NotMis:
        pass

    assert not isinstance(NotMis(), MisReportsAdapter)


def test_facade_exposes_each_backend():
    # The facade routes to each per-backend adapter.
    ann = FinXClient.__annotations__
    assert set(ann) == {"dotnet", "go", "mis", "mf", "coti"}
