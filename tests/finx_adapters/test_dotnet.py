"""Task 3 — .NET middleware adapter (finx.choiceindia.com/api/middleware).

Assertions derive from the proposal endpoint table (rows 1-6) and the frozen
request models: correct URL, ``authorization: <SessionId>`` header AND SessionId
in the PascalCase body, ``{Status,Response,Reason}`` parsing, HTTP-401 ->
FinXAuthError, and the per-endpoint identity/enum traps.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.finx.adapters.dotnet import DotNetMiddlewareAdapterImpl
from app.finx.adapters.errors import FinXAuthError
from app.finx.envelopes import Outcome
from app.finx.interfaces import DotNetMiddlewareAdapter
from app.finx.models import (
    GetDetailedPNLRequest,
    GetGlobalPNLNewRequest,
    GetLedgerDetailsRequest,
    LedgerPdfRequest,
    PnlPdfRequest,
    TaxReportRequest,
)

BASE = "https://finx.choiceindia.com/api/middleware"
SESSION = "SESS-TEST-0001"


@pytest.fixture
def adapter(transport, credentials):
    return DotNetMiddlewareAdapterImpl(transport, credentials)


def _last_request(route) -> tuple[dict, dict]:
    req = route.calls.last.request
    return dict(req.headers), json.loads(req.content)


def _pnl_pdf_req(request_for: int = 0) -> PnlPdfRequest:
    return PnlPdfRequest(
        ClientId="C123",
        UserId="C123",
        Group="Cash",
        FromDate="2024-04-01",
        ToDate="2025-03-31",
        RequestFor=request_for,
        SessionId=SESSION,
    )


def test_impl_satisfies_protocol(adapter):
    assert isinstance(adapter, DotNetMiddlewareAdapter)


@respx.mock
async def test_pnl_pdf_download_url(adapter, finx_fixture):
    route = respx.post(f"{BASE}/GetGlobalPNLPDF").mock(
        return_value=httpx.Response(200, json=finx_fixture("pnl_download_success"))
    )
    env = await adapter.get_global_pnl_pdf(_pnl_pdf_req(request_for=0))
    assert env.outcome is Outcome.success
    assert env.payload.startswith("https://client-report.choiceindia.com/")
    headers, body = _last_request(route)
    assert headers["authorization"] == SESSION  # raw SessionId, no prefix
    assert body["SessionId"] == SESSION  # duplicated in body
    assert body["With_Exp"] is True  # boolean on the PDF endpoint
    assert body["RequestFor"] == 0


@respx.mock
async def test_pnl_email_confirmation_is_success_payload(adapter, finx_fixture):
    respx.post(f"{BASE}/GetGlobalPNLPDF").mock(
        return_value=httpx.Response(200, json=finx_fixture("pnl_email_success"))
    )
    env = await adapter.get_global_pnl_pdf(_pnl_pdf_req(request_for=1))
    assert env.outcome is Outcome.success
    assert "mail sent" in env.payload.lower()


@respx.mock
async def test_pnl_no_data_is_returned_not_raised(adapter, finx_fixture):
    respx.post(f"{BASE}/GetGlobalPNLPDF").mock(
        return_value=httpx.Response(200, json=finx_fixture("pnl_no_data"))
    )
    env = await adapter.get_global_pnl_pdf(_pnl_pdf_req())
    assert env.outcome is Outcome.no_data
    assert env.reason == "Data not found."


@respx.mock
async def test_dotnet_401_raises_auth_error(adapter, finx_fixture):
    respx.post(f"{BASE}/GetGlobalPNLPDF").mock(
        return_value=httpx.Response(401, json=finx_fixture("dotnet_401"))
    )
    with pytest.raises(FinXAuthError):
        await adapter.get_global_pnl_pdf(_pnl_pdf_req())


@respx.mock
async def test_ledger_pdf_uppercase_group_and_client_code_loginid(adapter, finx_fixture):
    route = respx.post(f"{BASE}/GetLedgerDetailsPDF").mock(
        return_value=httpx.Response(200, json=finx_fixture("ledger_pdf_success"))
    )
    req = LedgerPdfRequest(
        ClientId="C123", LoginId="C123", FromDate="2024-04-01",
        ToDate="2025-03-31", SessionId=SESSION,
    )
    env = await adapter.get_ledger_details_pdf(req)
    assert env.outcome is Outcome.success
    _, body = _last_request(route)
    assert body["Group"] == "GROUP1"  # uppercase on the PDF endpoint
    assert body["LoginId"] == "C123"  # client code, NOT "JIFFY"
    assert body["Margin"] == 0
    assert body["RequestFor"] == 0


@respx.mock
async def test_tax_report_request_for_two_and_failure_wording(adapter, finx_fixture):
    route = respx.post(f"{BASE}/GetTaxReportPDF").mock(
        return_value=httpx.Response(200, json=finx_fixture("tax_failure"))
    )
    req = TaxReportRequest(
        ClientId="C123", FinYear="2024-2025", RequestFor=2, FileFormat=1, SessionId=SESSION
    )
    env = await adapter.get_tax_report_pdf(req)
    # "Data not available." is a distinct no-data wording; parsed via NO_DATA_REASONS.
    assert env.outcome is Outcome.no_data
    assert env.reason == "Data not available."
    _, body = _last_request(route)
    assert body["RequestFor"] == 2  # download is 2 on Tax (not 0)
    assert body["FileFormat"] == 1


@respx.mock
async def test_global_pnl_new_sends_truthy_with_exp_and_parses_object(adapter, finx_fixture):
    route = respx.post(f"{BASE}/GetGlobalPNLNew").mock(
        return_value=httpx.Response(200, json=finx_fixture("global_pnl_new_object"))
    )
    req = GetGlobalPNLNewRequest(
        UserId="C123", ClientId="C123", Group="Cash",
        FromDate="2024-04-01", ToDate="2025-03-31", SessionId=SESSION,
    )
    env = await adapter.get_global_pnl_new(req)
    assert env.outcome is Outcome.success
    assert "Trades" in env.payload and "Expenses" in env.payload
    _, body = _last_request(route)
    assert body["With_Exp"] == 1  # int, truthy -> stable {Trades,Expenses} shape


@respx.mock
async def test_global_pnl_new_falsy_shape_still_parses_as_success(adapter, finx_fixture):
    respx.post(f"{BASE}/GetGlobalPNLNew").mock(
        return_value=httpx.Response(200, json=finx_fixture("global_pnl_new_falsy_array"))
    )
    req = GetGlobalPNLNewRequest(
        UserId="C123", ClientId="C123", Group="Cash",
        FromDate="2024-04-01", ToDate="2025-03-31", SessionId=SESSION,
    )
    env = await adapter.get_global_pnl_new(req)
    assert env.outcome is Outcome.success
    assert isinstance(env.payload, list)  # bare array when With_Exp is falsy


@respx.mock
async def test_detailed_pnl_sends_neuron_literal(adapter, finx_fixture):
    route = respx.post(f"{BASE}/GetDetailedPNL").mock(
        return_value=httpx.Response(200, json=finx_fixture("detailed_pnl_success"))
    )
    req = GetDetailedPNLRequest(
        ClientId="C123", FromDate="2024-04-01", ToDate="2025-03-31", SessionId=SESSION
    )
    env = await adapter.get_detailed_pnl(req)
    assert env.outcome is Outcome.success
    _, body = _last_request(route)
    assert body["UserId"] == "neuron"  # fixed literal
    assert body["Group"] == "Group1"


@respx.mock
async def test_ledger_details_data_sends_jiffy_literal(adapter, finx_fixture):
    route = respx.post(f"{BASE}/GetLedgerDetails").mock(
        return_value=httpx.Response(200, json=finx_fixture("ledger_details_success"))
    )
    req = GetLedgerDetailsRequest(
        ClientId="C123", FromDate="2024-04-01", ToDate="2025-03-31", SessionId=SESSION
    )
    env = await adapter.get_ledger_details(req)
    assert env.outcome is Outcome.success
    _, body = _last_request(route)
    assert body["LoginId"] == "JIFFY"  # literal, NOT the client code
    assert body["Group"] == "Group1"  # data-API casing (vs PDF "GROUP1")


@respx.mock
async def test_ledger_data_no_data(adapter, finx_fixture):
    respx.post(f"{BASE}/GetLedgerDetails").mock(
        return_value=httpx.Response(200, json=finx_fixture("ledger_no_data"))
    )
    req = GetLedgerDetailsRequest(
        ClientId="C123", FromDate="2024-04-01", ToDate="2025-03-31", SessionId=SESSION
    )
    env = await adapter.get_ledger_details(req)
    assert env.outcome is Outcome.no_data


@respx.mock
async def test_reason_is_present_for_server_log_but_url_not_logged(adapter, finx_fixture, log_capture):
    respx.post(f"{BASE}/GetGlobalPNLPDF").mock(
        return_value=httpx.Response(200, json=finx_fixture("pnl_download_success"))
    )
    env = await adapter.get_global_pnl_pdf(_pnl_pdf_req())
    logged = log_capture()
    # The report URL (in the success payload) must never reach a log sink.
    assert env.payload not in logged
    assert "client-report.choiceindia.com" not in logged
