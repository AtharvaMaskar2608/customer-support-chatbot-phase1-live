"""Thin async Freshdesk v2 HTTP client (server-side only).

Wraps ``httpx.AsyncClient`` for the five endpoints the ticketing tool needs:
create, add-note, list-by-requester, view, search. Auth is HTTP Basic
``base64("<FRESHDESK_API_KEY>:X")`` (04 §1). Every non-2xx is turned into a typed
``FreshdeskAPIError`` carrying the status, the Freshdesk validation ``code``/
``field`` and the ``Retry-After`` (429) — the *raw* reason is kept for
server-side logging and NEVER surfaced to the user (H8). This module logs
nothing itself; the tool layer logs status/code server-side and never a ticket
id or URL in the clear.
"""

from __future__ import annotations

from typing import Any

import httpx


class FreshdeskConfigError(RuntimeError):
    """Raised when the client is built without a resolvable API key."""


class FreshdeskAPIError(Exception):
    """A Freshdesk non-2xx response, parsed. ``reason`` is server-side only."""

    def __init__(
        self,
        status_code: int,
        *,
        code: str | None = None,
        field: str | None = None,
        retry_after: float | None = None,
        reason: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.field = field
        self.retry_after = retry_after
        self.reason = reason
        # The message intentionally excludes any URL / ticket id.
        super().__init__(f"Freshdesk API error {status_code} (code={code}, field={field})")


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class FreshdeskClient:
    """Async Freshdesk v2 client. ``api_root`` has no trailing slash."""

    def __init__(
        self,
        api_root: str,
        api_key: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_root = api_root.rstrip("/")
        self._auth = httpx.BasicAuth(api_key, "X")  # base64("<key>:X")
        self._headers = {"Content-Type": "application/json"}
        self._http = http
        self._timeout = timeout

    @classmethod
    def from_config(cls, config: Any, *, http: httpx.AsyncClient | None = None) -> "FreshdeskClient":
        if not config.api_key:
            raise FreshdeskConfigError(
                f"No Freshdesk API key: set {config.api_key_env} in the environment."
            )
        if not config.api_root:
            raise FreshdeskConfigError(
                f"No Freshdesk API root: set {config.api_root_env} in the environment."
            )
        return cls(config.api_root, config.api_key, http=http)

    # -- HTTP plumbing ----------------------------------------------------

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._api_root}{path}"
        if self._http is not None:
            resp = await self._http.request(
                method, url, auth=self._auth, headers=self._headers, **kwargs
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(
                    method, url, auth=self._auth, headers=self._headers, **kwargs
                )
        _raise_for_status(resp)
        return resp

    # -- endpoints --------------------------------------------------------

    async def create_ticket(self, payload: dict) -> dict:
        """``POST /tickets`` → the created ticket object (201)."""
        resp = await self._send("POST", "/tickets", json=payload)
        return resp.json()

    async def add_note(self, ticket_id: int | str, body: str, *, private: bool = True) -> dict:
        """``POST /tickets/{id}/notes`` — append a (private) note."""
        resp = await self._send(
            "POST", f"/tickets/{ticket_id}/notes", json={"body": body, "private": private}
        )
        return resp.json()

    async def list_by_external_id(self, external_id: str) -> list[dict]:
        """``GET /tickets?unique_external_id=…`` (real-time, no lag), most-recent
        first. Returns the ticket list (possibly empty)."""
        resp = await self._send(
            "GET",
            "/tickets",
            params={
                "unique_external_id": external_id,
                "order_by": "updated_at",
                "order_type": "desc",
            },
        )
        data = resp.json()
        return data if isinstance(data, list) else []

    async def get_ticket(self, ticket_id: int | str, *, include: str | None = "stats") -> dict:
        """``GET /tickets/{id}`` (optionally ``?include=stats``)."""
        params = {"include": include} if include else None
        resp = await self._send("GET", f"/tickets/{ticket_id}", params=params)
        return resp.json()

    async def search_tickets(self, query: str) -> dict:
        """``GET /search/tickets?query="…"`` — secondary/reporting only (index lags
        minutes; never the sole dedupe gate). Returns ``{total, results}``."""
        resp = await self._send("GET", "/search/tickets", params={"query": f'"{query}"'})
        return resp.json()


def _raise_for_status(resp: httpx.Response) -> None:
    """Turn any non-2xx into a ``FreshdeskAPIError`` with parsed code/field/
    retry_after; the raw body is retained as ``reason`` for server-side logging."""
    if 200 <= resp.status_code < 300:
        return

    code: str | None = None
    field: str | None = None
    reason: str | None = None
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 — non-JSON error body (e.g. 5xx HTML)
        body = None
    if isinstance(body, dict):
        reason = body.get("description")
        errors = body.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            code = errors[0].get("code")
            field = errors[0].get("field")

    raise FreshdeskAPIError(
        resp.status_code,
        code=code,
        field=field,
        retry_after=_parse_retry_after(resp.headers.get("Retry-After")),
        reason=reason,
    )
