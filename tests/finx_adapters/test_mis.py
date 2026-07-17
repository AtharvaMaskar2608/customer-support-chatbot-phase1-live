"""Task 5 — MIS reports adapter (CML).

Assertions derive from proposal row 10: the three MIS headers (authType/jwt +
authorization SSO-JWT + source FINX_ANDROID), the camelCase body, parsing via
parse_mis_envelope, the cmlLink location, and HTTP-401 -> FinXAuthError. CML must
never be handed the SessionId.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.finx.adapters.errors import FinXAuthError
from app.finx.adapters.mis import MisReportsAdapterImpl
from app.finx.envelopes import Outcome
from app.finx.interfaces import MisReportsAdapter
from app.finx.models import CmlBody, CmlRequest

URL = "https://finx.choiceindia.com/mis/reports/generate"
SESSION = "SESS-TEST-0001"
JWT = "jwt.sso.token"


@pytest.fixture
def adapter(transport, credentials):
    return MisReportsAdapterImpl(transport, credentials)


def test_impl_satisfies_protocol(adapter):
    assert isinstance(adapter, MisReportsAdapter)


@respx.mock
async def test_cml_success_headers_body_and_cml_link(adapter, finx_fixture):
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, json=finx_fixture("cml_success"))
    )
    env = await adapter.generate_report(CmlRequest(searchValue="C123"))
    assert env.outcome is Outcome.success
    parsed = CmlBody.model_validate(env.payload)
    assert parsed.cmlLink.startswith("https://onmedia.choiceindia.com/")

    req = route.calls.last.request
    headers = dict(req.headers)
    assert headers["authtype"] == "jwt"
    assert headers["authorization"] == JWT  # SSO JWT
    assert headers["source"] == "FINX_ANDROID"
    # CML must never be handed the SessionId.
    assert SESSION not in headers.values()
    body = json.loads(req.content)
    assert body == {"reportType": "cml", "searchBy": "client-id", "searchValue": "C123"}
    assert "SessionId" not in body


@respx.mock
async def test_cml_http_401_raises_auth_error(adapter, finx_fixture):
    respx.post(URL).mock(return_value=httpx.Response(401, json=finx_fixture("cml_401")))
    with pytest.raises(FinXAuthError):
        await adapter.generate_report(CmlRequest(searchValue="C123"))


@respx.mock
async def test_cml_link_never_logged(adapter, finx_fixture, log_capture):
    respx.post(URL).mock(return_value=httpx.Response(200, json=finx_fixture("cml_success")))
    env = await adapter.generate_report(CmlRequest(searchValue="C123"))
    cml_link = CmlBody.model_validate(env.payload).cmlLink
    logged = log_capture()
    assert cml_link not in logged
    assert "X-Amz-Signature" not in logged
