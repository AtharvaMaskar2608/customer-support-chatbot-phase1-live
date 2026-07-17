"""Task 7 — COTI (finxomne) holdings adapter.

Assertions derive from proposal row 12: three credentials at once (Session-prefixed
SessionId header + ssotoken SSO-JWT header + body accessToken FINX-JWT), the
{Status,Response,Reason} envelope with lDictHoldingData keyed by ISIN, and that
the SessionId and both JWTs never reach a log sink. Flow is BLOCKED but the
transport is complete.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.finx.adapters.coti import FinxOmneCotiAdapterImpl
from app.finx.adapters.errors import FinXAuthError
from app.finx.envelopes import Outcome
from app.finx.interfaces import FinxOmneCotiAdapter
from app.finx.models import HoldingsRequest, HoldingsResponseBody

URL = "https://finxomne.choiceindia.com/COTI/V1/Holdings"
SESSION = "SESS-TEST-0001"
SSO_JWT = "jwt.sso.token"
FINX_JWT = "finx.issued.jwt"
ISIN = "INE002A01018"

HOLDINGS_RESPONSE = {
    "Status": "Success",
    "Reason": "",
    "Response": {
        "lDictHoldingData": {
            ISIN: {"LTP": 130330, "CP": 130000, "ABP": 1290.0, "ASP": 1303.3}
        },
        "BodStatus": 1,
    },
}


@pytest.fixture
def adapter(transport, credentials):
    return FinxOmneCotiAdapterImpl(transport, credentials)


def _req() -> HoldingsRequest:
    return HoldingsRequest(
        UserCode="C123", UserId="C123", SessionId=SESSION, accessToken=FINX_JWT
    )


def test_impl_satisfies_protocol(adapter):
    assert isinstance(adapter, FinxOmneCotiAdapter)


@respx.mock
async def test_three_credentials_wired_and_holdings_keyed_by_isin(adapter, log_capture):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=HOLDINGS_RESPONSE))
    env = await adapter.get_holdings(_req())
    assert env.outcome is Outcome.success
    parsed = HoldingsResponseBody.model_validate(env.payload)
    assert set(parsed.lDictHoldingData) == {ISIN}  # object keyed by ISIN

    req = route.calls.last.request
    headers = dict(req.headers)
    assert headers["authorization"] == f"Session {SESSION}"  # Session-prefixed
    assert headers["ssotoken"] == SSO_JWT  # SSO JWT header
    body = json.loads(req.content)
    assert body["GroupId"] == "HO"
    assert body["accessToken"] == FINX_JWT  # caller-supplied FINX JWT in body
    assert body["SessionId"] == SESSION

    # SessionId and both JWTs must never reach a log sink.
    logged = log_capture()
    for secret in (SESSION, SSO_JWT, FINX_JWT):
        assert secret not in logged


@respx.mock
async def test_401_raises_auth_error(adapter, finx_fixture):
    respx.post(URL).mock(return_value=httpx.Response(401, json=finx_fixture("dotnet_401")))
    with pytest.raises(FinXAuthError):
        await adapter.get_holdings(_req())


@respx.mock
async def test_business_fail_is_returned_not_raised(adapter):
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"Status": "Fail", "Response": None, "Reason": "x"})
    )
    env = await adapter.get_holdings(_req())
    assert env.outcome is Outcome.error  # in-band failure returned, never raised
