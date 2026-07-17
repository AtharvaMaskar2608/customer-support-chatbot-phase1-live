"""Task 6 — MF profile adapter (Phase-2 greeting, HEAVY PII).

Assertions derive from proposal row 11: auth is the SSO JWT, the body is
{InvCode}, and a successful response is reduced to ONLY the first name at the
transport boundary — no PAN/email/mobile/DOB/bank value ever appears in the
returned envelope or any log sink.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.finx.adapters.errors import FinXAuthError
from app.finx.adapters.mf import MfProfileAdapterImpl
from app.finx.envelopes import Outcome
from app.finx.interfaces import MfProfileAdapter
from app.finx.models import GetProfileRequest

URL = "https://mf.choiceindia.com/api/v2/investor/profile/extended"
JWT = "jwt.sso.token"

# A heavy-PII profile response. Every secret below must be discarded at the
# transport boundary — only the first name may survive.
PAN = "ABCPK1234Z"
EMAIL = "rajesh.sharma@example.com"
MOBILE = "9876543210"
PROFILE_RESPONSE = {
    "Status": "Success",
    "Reason": "",
    "Response": {
        "FirstHolderName": "RAJESH KUMAR SHARMA",
        "PAN": PAN,
        "Email": EMAIL,
        "Mobile": MOBILE,
        "DOB": "1980-01-01",
        "Address": "42 Nowhere Street, Mumbai",
        "Bank": [{"AccountNumber": "000111222333"}],
    },
}


@pytest.fixture
def adapter(transport, credentials):
    return MfProfileAdapterImpl(transport, credentials)


def test_impl_satisfies_protocol(adapter):
    assert isinstance(adapter, MfProfileAdapter)


@respx.mock
async def test_success_returns_only_first_name(adapter, log_capture):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=PROFILE_RESPONSE))
    env = await adapter.get_profile_extended(GetProfileRequest(InvCode="C123"))
    assert env.outcome is Outcome.success
    assert env.payload == "Rajesh"  # first token, title-cased; heavy PII dropped

    # The full profile object never becomes the payload, is never logged.
    returned = env.model_dump_json()
    haystack = returned + "\n" + log_capture()
    for secret in (PAN, EMAIL, MOBILE, "000111222333", "Nowhere", "1980-01-01"):
        assert secret not in haystack

    req = route.calls.last.request
    assert dict(req.headers)["authorization"] == JWT  # SSO JWT, not SessionId
    assert json.loads(req.content) == {"InvCode": "C123"}


@respx.mock
async def test_success_with_null_response_yields_none_first_name(adapter):
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"Status": "Success", "Response": None, "Reason": ""})
    )
    env = await adapter.get_profile_extended(GetProfileRequest(InvCode="C123"))
    assert env.outcome is Outcome.success
    assert env.payload is None


@respx.mock
async def test_error_discards_any_payload(adapter):
    respx.post(URL).mock(
        return_value=httpx.Response(
            200, json={"Status": "Fail", "Response": {"PAN": PAN}, "Reason": "nope"}
        )
    )
    env = await adapter.get_profile_extended(GetProfileRequest(InvCode="C123"))
    assert env.outcome is Outcome.error
    assert env.payload is None  # no PII escapes even on a failure envelope
    assert PAN not in env.model_dump_json()


@respx.mock
async def test_401_raises_auth_error(adapter, finx_fixture):
    respx.post(URL).mock(return_value=httpx.Response(401, json=finx_fixture("dotnet_401")))
    with pytest.raises(FinXAuthError):
        await adapter.get_profile_extended(GetProfileRequest(InvCode="C123"))
