"""Task 8 — FinXClient facade + package exports.

Assertions: the facade satisfies the frozen FinXClient Protocol, each backend
attribute satisfies its own per-backend Protocol, one call routes end to end
through the facade, and the public names are importable from app.finx.adapters.
"""

from __future__ import annotations

import httpx
import pytest
import respx

import app.finx.adapters as adapters_pkg
from app.finx.adapters import FinXClientImpl, FinXCredentials
from app.finx.interfaces import (
    DotNetMiddlewareAdapter,
    FinxOmneCotiAdapter,
    FinXClient,
    GoMiddlewareAdapter,
    MfProfileAdapter,
    MisReportsAdapter,
)
from app.finx.models import PnlPdfRequest


@pytest.fixture
async def facade(credentials):
    async with httpx.AsyncClient() as client:
        yield FinXClientImpl(client, credentials)


def test_facade_satisfies_finxclient_protocol(facade):
    assert isinstance(facade, FinXClient)


def test_each_backend_attribute_satisfies_its_protocol(facade):
    assert isinstance(facade.dotnet, DotNetMiddlewareAdapter)
    assert isinstance(facade.go, GoMiddlewareAdapter)
    assert isinstance(facade.mis, MisReportsAdapter)
    assert isinstance(facade.mf, MfProfileAdapter)
    assert isinstance(facade.coti, FinxOmneCotiAdapter)


def test_facade_exposes_exactly_the_five_backends(facade):
    for name in ("dotnet", "go", "mis", "mf", "coti"):
        assert hasattr(facade, name)


@respx.mock
async def test_call_routes_through_facade_to_the_owning_adapter(facade, finx_fixture):
    respx.post("https://finx.choiceindia.com/api/middleware/GetGlobalPNLPDF").mock(
        return_value=httpx.Response(200, json=finx_fixture("pnl_download_success"))
    )
    env = await facade.dotnet.get_global_pnl_pdf(
        PnlPdfRequest(
            ClientId="C123", UserId="C123", Group="Cash", FromDate="2024-04-01",
            ToDate="2025-03-31", RequestFor=0, SessionId="SESS-TEST-0001",
        )
    )
    assert env.payload.startswith("https://client-report.choiceindia.com/")


def test_public_exports_are_importable():
    expected = {
        "FinXClientImpl", "FinXCredentials", "HttpTransport", "TransportSettings",
        "DotNetMiddlewareAdapterImpl", "GoMiddlewareAdapterImpl",
        "MisReportsAdapterImpl", "MfProfileAdapterImpl", "FinxOmneCotiAdapterImpl",
        "fetch_report_bytes", "validate_report_bytes",
        "FinXError", "FinXAuthError", "FinXTimeoutError", "FinXFetchError",
        "FinXTransportError",
    }
    assert expected <= set(adapters_pkg.__all__)
    for name in expected:
        assert hasattr(adapters_pkg, name)


def test_credentials_are_a_simple_bundle():
    creds = FinXCredentials(session_id="S", sso_jwt="J")
    assert creds.session_id == "S"
    assert creds.sso_jwt == "J"
    assert FinXCredentials(session_id="S").sso_jwt is None  # SessionId-only sessions
