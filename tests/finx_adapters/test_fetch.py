"""Task 2 — server-side byte fetch + the shared validation primitive.

Assertions come from the proposal's "Server-side byte-fetch helper" bullet and
the doneCondition: accept ``%PDF`` / ``PK`` bytes above the frozen size floor;
raise ``FinXFetchError`` on short/empty/wrong-magic; raise ``FinXTimeoutError``
on network/timeout; never log the URL.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.contracts.flow import ByteValidation
from app.contracts.router import ReportFormat
from app.finx.adapters.errors import FinXFetchError, FinXTimeoutError
from app.finx.adapters.fetch import fetch_report_bytes, validate_report_bytes

FLOOR = ByteValidation().min_bytes  # frozen size floor (1024)
PDF_URL = "https://client-report.choiceindia.com/PDFReports/PNL_x.pdf"
CML_URL = "https://onmedia.choiceindia.com/JF/h/h_CML.pdf?X-Amz-Signature=SECRETSIG"


def _pdf(size: int = FLOOR + 512) -> bytes:
    body = b"%PDF-1.7\n" + b"0" * size
    return body[: max(size, len(b"%PDF-1.7\n"))]


def _xlsx(size: int = FLOOR + 512) -> bytes:
    return b"PK\x03\x04" + b"0" * size


# --- the shared validation primitive (used by fetch AND the Go download) ----


def test_validate_accepts_pdf_above_floor():
    data = _pdf()
    assert validate_report_bytes(data, ReportFormat.pdf) is data


def test_validate_accepts_xlsx_above_floor():
    # Frozen excel magic is b"PK" (2 bytes), not PK\x03\x04 — the real zip header
    # still starts with PK so it validates.
    data = _xlsx()
    assert validate_report_bytes(data, ReportFormat.excel) is data


def test_validate_rejects_empty():
    with pytest.raises(FinXFetchError):
        validate_report_bytes(b"", ReportFormat.pdf)


def test_validate_rejects_below_size_floor():
    with pytest.raises(FinXFetchError):
        validate_report_bytes(b"%PDF", ReportFormat.pdf)  # 4 bytes < floor


def test_validate_rejects_wrong_magic_above_floor():
    with pytest.raises(FinXFetchError):
        validate_report_bytes(b"XXXX" + b"0" * (FLOOR + 8), ReportFormat.pdf)


def test_validate_pdf_bytes_are_not_a_valid_xlsx():
    with pytest.raises(FinXFetchError):
        validate_report_bytes(_pdf(), ReportFormat.excel)


# --- fetch_report_bytes end to end -----------------------------------------


@respx.mock
async def test_fetch_returns_validated_pdf_bytes():
    data = _pdf()
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=data))
    out = await fetch_report_bytes(PDF_URL, expected_format=ReportFormat.pdf)
    assert out == data


@respx.mock
async def test_fetch_from_signed_cloudfront_url_does_not_depend_on_signature():
    # FLAG B: fetch the S3/CloudFront pre-signed URL immediately, server-side.
    data = _pdf()
    respx.get(CML_URL).mock(return_value=httpx.Response(200, content=data))
    out = await fetch_report_bytes(CML_URL, expected_format=ReportFormat.pdf)
    assert out == data


@respx.mock
async def test_fetch_short_body_raises_fetch_error():
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=b"%PDF"))
    with pytest.raises(FinXFetchError):
        await fetch_report_bytes(PDF_URL, expected_format=ReportFormat.pdf)


@respx.mock
async def test_fetch_wrong_magic_raises_fetch_error():
    respx.get(PDF_URL).mock(
        return_value=httpx.Response(200, content=b"<html>" + b"0" * (FLOOR + 8))
    )
    with pytest.raises(FinXFetchError):
        await fetch_report_bytes(PDF_URL, expected_format=ReportFormat.pdf)


@respx.mock
async def test_fetch_404_raises_fetch_error():
    respx.get(PDF_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(FinXFetchError):
        await fetch_report_bytes(PDF_URL, expected_format=ReportFormat.pdf)


@respx.mock
async def test_fetch_persistent_5xx_raises_fetch_error():
    respx.get(PDF_URL).mock(return_value=httpx.Response(502))
    with pytest.raises(FinXFetchError):
        await fetch_report_bytes(PDF_URL, expected_format=ReportFormat.pdf)


@respx.mock
async def test_fetch_timeout_raises_timeout_error():
    respx.get(PDF_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(FinXTimeoutError):
        await fetch_report_bytes(PDF_URL, expected_format=ReportFormat.pdf)


@respx.mock
async def test_fetch_never_logs_the_signed_url(log_capture):
    data = _pdf()
    respx.get(CML_URL).mock(return_value=httpx.Response(200, content=data))
    await fetch_report_bytes(CML_URL, expected_format=ReportFormat.pdf)
    logged = log_capture()
    assert "SECRETSIG" not in logged
    assert "onmedia.choiceindia.com" not in logged
