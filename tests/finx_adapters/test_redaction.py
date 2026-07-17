"""Task 9 — consolidated logging-redaction / no-leak sweep.

The proposal's "Logging discipline" invariant, exercised across every adapter and
the byte-fetch helper at once: no report URL, file_id, signed query string,
SessionId, JWT, cmlLink, or PII substring reaches any log sink. The server-side
``reason`` MAY be logged and MAY appear in ``ParsedEnvelope.reason`` — but no
sensitive handle ever does.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.finx.adapters import FinXClientImpl, FinXCredentials, fetch_report_bytes
from app.contracts.router import ReportFormat
from app.finx.models import (
    BrokerageSlabRequest,
    CmlRequest,
    ContractNoteDownloadRequest,
    ContractNoteListRequest,
    GetProfileRequest,
    HoldingsRequest,
    PnlPdfRequest,
)

# Distinctive secrets seeded into requests/responses; none may reach a log sink.
SESSION = "SESS-SECRET-9999"
SSO_JWT = "SECRET.SSO.JWT.VALUE"
FINX_JWT = "SECRET.FINX.JWT.VALUE"
REPORT_URL = "https://client-report.choiceindia.com/PDFReports/SECRET_REPORT_ID.pdf"
FILE_ID = "SECRET_FILE_ID_TOKEN_88CHARS"
CML_SIG = "SECRETSIGNATUREVALUE"
CML_LINK = f"https://onmedia.choiceindia.com/JF/h/CML.pdf?X-Amz-Signature={CML_SIG}"
PAN = "SECRETPAN99Z"

ALL_SECRETS = [SESSION, SSO_JWT, FINX_JWT, REPORT_URL, FILE_ID, CML_SIG, CML_LINK, PAN,
               "client-report.choiceindia.com", "onmedia.choiceindia.com"]


@pytest.fixture
async def facade():
    creds = FinXCredentials(session_id=SESSION, sso_jwt=SSO_JWT)
    async with httpx.AsyncClient() as client:
        yield FinXClientImpl(client, creds)


def _pdf() -> bytes:
    return b"%PDF-1.7\n" + b"0" * 2048


@respx.mock
async def test_no_secret_reaches_a_log_sink_across_all_adapters(facade, log_capture):
    respx.post("https://finx.choiceindia.com/api/middleware/GetGlobalPNLPDF").mock(
        return_value=httpx.Response(200, json={"Status": "Success", "Response": REPORT_URL, "Reason": ""})
    )
    respx.post("https://finx.choiceindia.com/middleware-go/report/contract").mock(
        return_value=httpx.Response(
            200, json={"StatusCode": 200, "Message": "ok", "Body": {"client_code": "C", "contractNotes": []}}
        )
    )
    respx.post("https://api.choiceindia.com/middleware-go/contract/download").mock(
        return_value=httpx.Response(200, content=_pdf())
    )
    respx.post("https://api.choiceindia.com/middleware-go/v2/get-brokerage-slab").mock(
        return_value=httpx.Response(200, json={"StatusCode": 200, "Status": "Success", "Response": [], "Reason": ""})
    )
    respx.post("https://finx.choiceindia.com/mis/reports/generate").mock(
        return_value=httpx.Response(200, json={"statusCode": 200, "message": "ok", "body": {"cmlLink": CML_LINK}})
    )
    respx.post("https://mf.choiceindia.com/api/v2/investor/profile/extended").mock(
        return_value=httpx.Response(200, json={"Status": "Success", "Response": {"FirstHolderName": "Asha Rao", "PAN": PAN}, "Reason": ""})
    )
    respx.post("https://finxomne.choiceindia.com/COTI/V1/Holdings").mock(
        return_value=httpx.Response(200, json={"Status": "Success", "Response": {"lDictHoldingData": {}}, "Reason": ""})
    )
    respx.get(CML_LINK).mock(return_value=httpx.Response(200, content=_pdf()))

    await facade.dotnet.get_global_pnl_pdf(
        PnlPdfRequest(ClientId="C", UserId="C", Group="Cash", FromDate="2024-04-01",
                      ToDate="2025-03-31", RequestFor=0, SessionId=SESSION)
    )
    await facade.go.list_contract_notes(
        ContractNoteListRequest(client_id="C", from_date="2024-09-01", to_date="2024-09-30")
    )
    await facade.go.download_contract_note(
        ContractNoteDownloadRequest(client_code="C", file_id=FILE_ID)
    )
    await facade.go.get_brokerage_slab(BrokerageSlabRequest(ClientID="C"))
    await facade.mis.generate_report(CmlRequest(searchValue="C"))
    await facade.mf.get_profile_extended(GetProfileRequest(InvCode="C"))
    await facade.coti.get_holdings(
        HoldingsRequest(UserCode="C", UserId="C", SessionId=SESSION, accessToken=FINX_JWT)
    )
    await fetch_report_bytes(CML_LINK, expected_format=ReportFormat.pdf)

    logged = log_capture()
    for secret in ALL_SECRETS:
        assert secret not in logged, f"secret leaked into a log sink: {secret!r}"
    # Sanity: the transport DID log diagnostics (endpoint labels), just not secrets.
    assert "endpoint=" in logged


@respx.mock
async def test_profile_pii_never_becomes_returned_payload(facade):
    respx.post("https://mf.choiceindia.com/api/v2/investor/profile/extended").mock(
        return_value=httpx.Response(
            200, json={"Status": "Success", "Response": {"FirstHolderName": "Asha Rao", "PAN": PAN}, "Reason": ""}
        )
    )
    env = await facade.mf.get_profile_extended(GetProfileRequest(InvCode="C"))
    assert env.payload == "Asha"
    assert PAN not in env.model_dump_json()
