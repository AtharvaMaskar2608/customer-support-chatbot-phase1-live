"""Shared HTTP transport for the FinX adapters (timeout / retry / logging).

One place owns the cross-cutting transport policy so every per-backend adapter
inherits it identically:

- **Bounded timeouts** on every call (connect + read), from module-local
  :class:`TransportSettings` with sensible defaults. Remote-tunability, if ever
  wanted, is a ``contracts-foundation`` follow-up — this layer keeps the values
  local and does not touch the frozen remote-config schema.
- **At most one bounded retry** for transport-transient failures (connection
  reset, DNS, timeout, 5xx). Timeouts and network failures raise
  :class:`FinXTimeoutError`; a persistent 5xx raises :class:`FinXTransportError`.
  In-band business failures (HTTP 200 with an envelope ``Fail``) are NEVER
  retried here — the engine owns the regenerate-once policy.
- **Logging discipline** — diagnostic logs carry the endpoint label, the HTTP
  status, and the latency only. Report URLs, ``file_id``, signed query strings,
  ``SessionId``, JWTs, and PII never reach any sink. The endpoint *label* passed
  by callers is a fixed backend method name, never a URL with a query string.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.finx.adapters.errors import FinXAuthError, FinXTimeoutError, FinXTransportError
from app.finx.envelopes import Outcome, ParsedEnvelope
from app.finx.models import EndpointSpec

logger = logging.getLogger("app.finx.adapters")


def raise_for_auth(env: ParsedEnvelope) -> ParsedEnvelope:
    """The single auth-mapping site: an ``auth_error`` outcome (HTTP 401, detected
    by the frozen parsers on ``http_status``) becomes a raised
    :class:`FinXAuthError`. Every JSON-envelope adapter routes through this so
    401 handling is identical across backends. Returns the envelope unchanged for
    any non-auth outcome (success / no_data / error are returned, never raised)."""
    if env.outcome is Outcome.auth_error:
        raise FinXAuthError("finx auth failed", reason=env.reason)
    return env


@dataclass(frozen=True)
class TransportSettings:
    """Module-local timeout / retry policy (not the frozen remote-config)."""

    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    max_retries: int = 1  # at most one bounded retry for transient failures


DEFAULT_SETTINGS = TransportSettings()


def endpoint_url(spec: EndpointSpec) -> str:
    """Build the absolute HTTPS URL for a frozen endpoint descriptor."""
    return f"https://{spec.host}{spec.path}"


async def send_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    endpoint: str,
    settings: TransportSettings = DEFAULT_SETTINGS,
    json: object | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Issue one request with the bounded timeout + single-retry policy.

    Returns the :class:`httpx.Response` for any non-5xx status (including 401,
    which the caller maps to an auth error). Raises :class:`FinXTimeoutError` on
    timeout/network failure that survives the retry, and
    :class:`FinXTransportError` on a 5xx that survives the retry.
    """
    timeout = httpx.Timeout(
        connect=settings.connect_timeout,
        read=settings.read_timeout,
        write=settings.read_timeout,
        pool=settings.connect_timeout,
    )
    attempts = settings.max_retries + 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            response = await client.request(
                method, url, json=json, headers=headers, timeout=timeout
            )
        except httpx.TransportError as exc:
            # Timeouts and network errors (DNS, connection reset, read error)
            # are all httpx.TransportError. Transient: retry, then FinXTimeoutError.
            last_exc = exc
            logger.info("finx endpoint=%s transport_error attempt=%d", endpoint, attempt)
            continue
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "finx endpoint=%s status=%d latency_ms=%d",
            endpoint,
            response.status_code,
            latency_ms,
        )
        if response.status_code >= 500:
            if attempt + 1 < attempts:
                continue  # bounded retry for a transient 5xx
            raise FinXTransportError(f"upstream {response.status_code} at {endpoint}")
        return response
    raise FinXTimeoutError(f"transport failure at {endpoint}") from last_exc


class HttpTransport:
    """Thin wrapper over an :class:`httpx.AsyncClient` applying the shared policy.

    The client is owned by the caller (the facade); this wrapper never closes it.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        settings: TransportSettings = DEFAULT_SETTINGS,
    ) -> None:
        self._client = client
        self._settings = settings

    async def post_json(
        self, url: str, *, endpoint: str, headers: dict[str, str], json: object
    ) -> tuple[int, dict]:
        """POST a JSON body; return ``(status_code, parsed_body_dict)``.

        Raises :class:`FinXTransportError` if the body is not a JSON object.
        """
        response = await send_with_retry(
            self._client,
            "POST",
            url,
            endpoint=endpoint,
            settings=self._settings,
            json=json,
            headers=headers,
        )
        try:
            body = response.json()
        except ValueError:  # includes json.JSONDecodeError
            body = None
        if not isinstance(body, dict):
            # Auth failure is detected by HTTP status, NOT body shape (the frozen
            # envelope parsers key 401 on http_status before parsing) — a malformed
            # or empty 401 body must still surface as auth, never a transport error.
            if response.status_code == 401:
                return response.status_code, {}
            raise FinXTransportError(f"non-JSON body from {endpoint}")
        return response.status_code, body

    async def post_bytes(
        self, url: str, *, endpoint: str, headers: dict[str, str], json: object
    ) -> tuple[int, bytes]:
        """POST a JSON body and return ``(status_code, raw_body_bytes)`` — for the
        per-note download that answers with ``application/pdf`` bytes, not JSON."""
        response = await send_with_retry(
            self._client,
            "POST",
            url,
            endpoint=endpoint,
            settings=self._settings,
            json=json,
            headers=headers,
        )
        return response.status_code, response.content

    async def get_bytes(self, url: str, *, endpoint: str) -> tuple[int, bytes]:
        """GET a (possibly unauthenticated, signed) report URL server-side and
        return ``(status_code, raw_body_bytes)``. The URL is never logged."""
        response = await send_with_retry(
            self._client, "GET", url, endpoint=endpoint, settings=self._settings
        )
        return response.status_code, response.content
