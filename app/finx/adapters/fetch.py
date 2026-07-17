"""Server-side report byte fetch + the shared magic-byte/size-floor primitive.

FinX report handles (the PNL/Ledger/Tax report URLs on
``client-report.choiceindia.com`` and the CML ``cmlLink`` on the CloudFront/S3
``onmedia.choiceindia.com`` pre-signed URL) are fetched HERE, server-side, and
only the raw bytes flow onward — the URL and any signed query string never reach
the client or the logs. The CloudFront 120s / single-use signature is NOT relied
on as a security boundary (FLAG B); the bytes are fetched immediately.

Validation is the FROZEN ``ByteValidation`` config from ``app/contracts/flow.py``
(``min_bytes`` size floor + ``%PDF`` / ``PK`` magic bytes) — this change consumes
that config, it does not define its own. The same primitive validates the Go
per-note download, which returns raw ``application/pdf`` bytes directly.
"""

from __future__ import annotations

import httpx

from app.contracts.flow import ByteValidation
from app.contracts.router import ReportFormat
from app.finx.adapters.base import HttpTransport
from app.finx.adapters.errors import FinXFetchError, FinXTransportError

#: The frozen size-floor + magic-byte config. Instantiated once (defaults only).
_VALIDATION = ByteValidation()


def _expected_magic(expected_format: ReportFormat) -> bytes:
    if expected_format is ReportFormat.pdf:
        return _VALIDATION.pdf_magic  # b"%PDF"
    if expected_format is ReportFormat.excel:
        return _VALIDATION.excel_magic  # b"PK" (zip/xlsx header)
    raise FinXFetchError(f"unsupported report format {expected_format!r}")


def validate_report_bytes(data: bytes, expected_format: ReportFormat) -> bytes:
    """Apply the frozen size-floor + magic-byte check; return the bytes unchanged.

    Raises :class:`FinXFetchError` when ``data`` is empty, below ``min_bytes``, or
    does not start with the format's magic bytes. Shared by ``fetch_report_bytes``
    and the Go per-note download so both delivery paths validate identically.
    """
    if len(data) < _VALIDATION.min_bytes:
        raise FinXFetchError("report bytes below the size floor")
    if not data.startswith(_expected_magic(expected_format)):
        raise FinXFetchError("report bytes failed the magic-byte check")
    return data


async def fetch_report_bytes(url: str, *, expected_format: ReportFormat) -> bytes:
    """GET a FinX-issued report URL server-side and return validated raw bytes.

    Raises :class:`FinXFetchError` on a non-200 URL response or bytes that fail
    validation, and :class:`~app.finx.adapters.errors.FinXTimeoutError` on a
    network/timeout failure. The URL is never logged or returned.
    """
    async with httpx.AsyncClient() as client:
        transport = HttpTransport(client)
        try:
            status, data = await transport.get_bytes(url, endpoint="fetch_report")
        except FinXTransportError as exc:
            # A persistent 5xx on the report URL is an E-FETCH condition (the
            # report generated but did not arrive), not an engine-level unknown.
            raise FinXFetchError("report url unavailable", reason=exc.reason) from exc
    if status != 200:
        raise FinXFetchError(f"report url returned HTTP {status}")
    return validate_report_bytes(data, expected_format)
