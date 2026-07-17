"""Task 4 — Go middleware adapter (contract list / per-note download / brokerage).

Assertions derive from proposal rows 7-9 and the frozen models: the contract
list uses the SessionId header ONLY (no body SessionId, FLAG A), the download is
"Session "-prefixed and returns validated raw PDF bytes, and the brokerage hybrid
envelope is parsed via the .NET parser with ``desc`` rendered verbatim.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.finx.adapters.errors import FinXAuthError, FinXFetchError
from app.finx.adapters.go import GoMiddlewareAdapterImpl
from app.finx.envelopes import Outcome
from app.finx.interfaces import GoMiddlewareAdapter
from app.finx.models import (
    BrokerageSlabRequest,
    ContractNoteDownloadRequest,
    ContractNoteListBody,
    ContractNoteListRequest,
)

LIST_URL = "https://finx.choiceindia.com/middleware-go/report/contract"
DL_URL = "https://api.choiceindia.com/middleware-go/contract/download"
BROK_URL = "https://api.choiceindia.com/middleware-go/v2/get-brokerage-slab"
SESSION = "SESS-TEST-0001"
JWT = "jwt.sso.token"


@pytest.fixture
def adapter(transport, credentials):
    return GoMiddlewareAdapterImpl(transport, credentials)


def _last_request(route) -> tuple[dict, bytes]:
    req = route.calls.last.request
    return dict(req.headers), req.content


def _pdf_bytes() -> bytes:
    return b"%PDF-1.7\n" + b"0" * 2048


def test_impl_satisfies_protocol(adapter):
    assert isinstance(adapter, GoMiddlewareAdapter)


@respx.mock
async def test_contract_list_header_only_auth_no_body_session(adapter, finx_fixture):
    route = respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=finx_fixture("contract_note_list_success"))
    )
    req = ContractNoteListRequest(client_id="C123", from_date="2024-09-01", to_date="2024-09-30")
    env = await adapter.list_contract_notes(req)
    assert env.outcome is Outcome.success
    headers, content = _last_request(route)
    body = json.loads(content)
    assert headers["authorization"] == SESSION  # raw SessionId, no "Session " prefix
    assert "SessionId" not in body and "session_id" not in body  # FLAG A: none in body
    assert set(body) == {"client_id", "from_date", "to_date"}  # snake_case only


@respx.mock
async def test_contract_list_rows_keyed_by_file_id_not_id(adapter, finx_fixture):
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(200, json=finx_fixture("contract_note_list_success"))
    )
    req = ContractNoteListRequest(client_id="C123", from_date="2024-09-01", to_date="2024-09-30")
    env = await adapter.list_contract_notes(req)
    parsed = ContractNoteListBody.model_validate(env.payload)
    keyed = parsed.by_file_id()
    assert set(keyed) == {"<FILE_ID_TOKEN>", "<FILE_ID_TOKEN_2>"}  # keyed by file_id
    # group matched case-insensitively downstream: Grp1 and GRP1 both appear.
    assert {n.group for n in parsed.contractNotes} == {"Grp1", "GRP1"}


@respx.mock
async def test_contract_list_204_is_no_data(adapter, finx_fixture):
    respx.post(LIST_URL).mock(
        return_value=httpx.Response(204, json=finx_fixture("contract_note_204_no_data"))
    )
    req = ContractNoteListRequest(client_id="C123", from_date="2024-09-01", to_date="2024-09-30")
    env = await adapter.list_contract_notes(req)
    assert env.outcome is Outcome.no_data


@respx.mock
async def test_contract_list_401_raises_auth_error(adapter):
    respx.post(LIST_URL).mock(return_value=httpx.Response(401, json={"Message": "unauth"}))
    req = ContractNoteListRequest(client_id="C123", from_date="2024-09-01", to_date="2024-09-30")
    with pytest.raises(FinXAuthError):
        await adapter.list_contract_notes(req)


@respx.mock
async def test_download_session_prefixed_auth_returns_validated_bytes(adapter, log_capture):
    data = _pdf_bytes()
    route = respx.post(DL_URL).mock(return_value=httpx.Response(200, content=data))
    req = ContractNoteDownloadRequest(client_code="C123", file_id="SENSITIVE_FILE_ID_TOKEN")
    out = await adapter.download_contract_note(req)
    assert out == data
    headers, _ = _last_request(route)
    assert headers["authorization"] == f"Session {SESSION}"  # "Session " prefix
    # file_id is sensitive — must never reach a log sink.
    assert "SENSITIVE_FILE_ID_TOKEN" not in log_capture()


@respx.mock
async def test_download_short_bytes_raise_fetch_error(adapter):
    respx.post(DL_URL).mock(return_value=httpx.Response(200, content=b"%PDF"))
    req = ContractNoteDownloadRequest(client_code="C123", file_id="F")
    with pytest.raises(FinXFetchError):
        await adapter.download_contract_note(req)


@respx.mock
async def test_download_wrong_magic_raises_fetch_error(adapter):
    respx.post(DL_URL).mock(return_value=httpx.Response(200, content=b"<html>" + b"0" * 2048))
    req = ContractNoteDownloadRequest(client_code="C123", file_id="F")
    with pytest.raises(FinXFetchError):
        await adapter.download_contract_note(req)


@respx.mock
async def test_download_401_raises_auth_error(adapter):
    respx.post(DL_URL).mock(return_value=httpx.Response(401, content=b""))
    req = ContractNoteDownloadRequest(client_code="C123", file_id="F")
    with pytest.raises(FinXAuthError):
        await adapter.download_contract_note(req)


@respx.mock
async def test_download_404_raises_fetch_error_not_incidental_magic_pass(adapter):
    # A 404 error body that happens to start with %PDF above the floor must NOT be
    # accepted as a valid note — the non-200 guard rejects it before validation.
    respx.post(DL_URL).mock(
        return_value=httpx.Response(404, content=b"%PDF-fake-error-page" + b"0" * 2048)
    )
    req = ContractNoteDownloadRequest(client_code="C123", file_id="F")
    with pytest.raises(FinXFetchError):
        await adapter.download_contract_note(req)


@respx.mock
async def test_brokerage_hybrid_parses_via_dotnet_and_keeps_desc_verbatim(adapter, finx_fixture):
    route = respx.post(BROK_URL).mock(
        return_value=httpx.Response(200, json=finx_fixture("brokerage_hybrid_success"))
    )
    env = await adapter.get_brokerage_slab(BrokerageSlabRequest(ClientID="C123"))
    assert env.outcome is Outcome.success
    # payload is the raw dynamic group array — no hardcoded segments, no rupee math.
    assert isinstance(env.payload, list)
    first_desc = env.payload[0]["list"][0]["desc"]
    assert first_desc == "₹0.10 for trade value of 10 thousand"  # verbatim
    headers, content = _last_request(route)
    assert headers["authorization"] == JWT  # SSO JWT, not the SessionId
    assert json.loads(content) == {"ClientID": "C123"}
