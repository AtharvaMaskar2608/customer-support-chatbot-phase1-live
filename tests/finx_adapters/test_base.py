"""Task 1 — shared HTTP transport policy (timeout / retry / logging).

Every assertion is a promise from the proposal's "Timeout & retry policy" and
"Logging discipline" bullets, exercised against respx-mocked httpx.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.finx.adapters.base import HttpTransport, TransportSettings, send_with_retry
from app.finx.adapters.errors import FinXTimeoutError, FinXTransportError

URL = "https://finx.choiceindia.com/api/middleware/GetGlobalPNLPDF"


@respx.mock
async def test_post_json_returns_status_and_parsed_body(transport):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"Status": "Success"}))
    status, body = await transport.post_json(
        URL, endpoint="GetGlobalPNLPDF", headers={}, json={"x": 1}
    )
    assert status == 200
    assert body == {"Status": "Success"}


@respx.mock
async def test_401_is_returned_not_retried(transport):
    route = respx.post(URL).mock(
        return_value=httpx.Response(401, json={"Status": "Fail", "Reason": "Invalid SessionId"})
    )
    status, body = await transport.post_json(URL, endpoint="ep", headers={}, json={})
    assert status == 401
    assert route.call_count == 1  # auth failure is NOT a transient — never retried


@respx.mock
async def test_401_with_empty_body_still_returns_401(transport):
    # Auth is detected by HTTP status, not body shape: a malformed/empty 401 body
    # must still surface as 401 (-> the parser maps it to auth), not a transport error.
    respx.post(URL).mock(return_value=httpx.Response(401, text=""))
    status, body = await transport.post_json(URL, endpoint="ep", headers={}, json={})
    assert status == 401
    assert body == {}


@respx.mock
async def test_401_with_html_body_still_returns_401(transport):
    respx.post(URL).mock(return_value=httpx.Response(401, text="<html>nope</html>"))
    status, body = await transport.post_json(URL, endpoint="ep", headers={}, json={})
    assert status == 401
    assert body == {}


@respx.mock
async def test_business_fail_200_is_returned_not_retried(transport):
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, json={"Status": "Fail", "Reason": "Data not found."})
    )
    status, _ = await transport.post_json(URL, endpoint="ep", headers={}, json={})
    assert status == 200
    assert route.call_count == 1  # in-band business failure never retried here


@respx.mock
async def test_5xx_retries_once_then_raises_transport_error(transport):
    route = respx.post(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(FinXTransportError):
        await transport.post_json(URL, endpoint="ep", headers={}, json={})
    assert route.call_count == 2  # original + exactly one bounded retry


@respx.mock
async def test_5xx_then_success_recovers_within_the_retry(transport):
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"Status": "Success"})]
    )
    status, body = await transport.post_json(URL, endpoint="ep", headers={}, json={})
    assert status == 200
    assert route.call_count == 2


@respx.mock
async def test_timeout_raises_finx_timeout_after_one_retry(transport):
    route = respx.post(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(FinXTimeoutError):
        await transport.post_json(URL, endpoint="ep", headers={}, json={})
    assert route.call_count == 2


@respx.mock
async def test_network_error_raises_finx_timeout(transport):
    respx.post(URL).mock(side_effect=httpx.ConnectError("dns"))
    with pytest.raises(FinXTimeoutError):
        await transport.post_json(URL, endpoint="ep", headers={}, json={})


@respx.mock
async def test_non_json_body_raises_transport_error(transport):
    respx.post(URL).mock(return_value=httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(FinXTransportError):
        await transport.post_json(URL, endpoint="ep", headers={}, json={})


@respx.mock
async def test_get_bytes_returns_raw_content(transport):
    url = "https://client-report.choiceindia.com/PDFReports/x.pdf?sig=SECRET"
    respx.get(url).mock(return_value=httpx.Response(200, content=b"%PDF-1.7 body"))
    status, data = await transport.get_bytes(url, endpoint="fetch_report")
    assert status == 200
    assert data == b"%PDF-1.7 body"


@respx.mock
async def test_logs_never_contain_url_query_or_credentials(transport, log_capture):
    signed = "https://onmedia.choiceindia.com/x?X-Amz-Signature=TOPSECRETSIG"
    respx.get(signed).mock(return_value=httpx.Response(200, content=b"%PDF"))
    await transport.get_bytes(signed, endpoint="fetch_report")
    logged = log_capture()
    assert "TOPSECRETSIG" not in logged
    assert "X-Amz-Signature" not in logged
    # The endpoint label and status ARE allowed diagnostics.
    assert "fetch_report" in logged


@respx.mock
async def test_settings_are_module_local_and_tunable(transport):
    # A custom settings object drives retry count; proves values are not the
    # frozen remote-config (which this change must not touch).
    settings = TransportSettings(max_retries=0)
    route = respx.post(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FinXTransportError):
        await send_with_retry(
            transport._client, "POST", URL, endpoint="ep", settings=settings, json={}
        )
    assert route.call_count == 1  # max_retries=0 -> a single attempt
