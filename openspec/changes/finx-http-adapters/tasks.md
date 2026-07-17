# Tasks: finx-http-adapters

Decomposition of `proposal.md` into ordered, verifiable tasks. The proposal is
the contract; this is my working breakdown of it, never an expansion of scope.
All code lands under `app/finx/adapters/**`; all tests under
`tests/finx_adapters/**`. Frozen surfaces (`app/finx/interfaces.py`,
`app/finx/envelopes.py`, `app/finx/models.py`, `app/contracts/**`,
`app/config/**`) are imported read-only, never edited.

Cross-cutting design decisions (derived from the frozen surface + proposal):

- **Credentials.** The frozen adapter Protocol methods take only `req`. The
  frozen `FinXClient` docstring mandates the facade "forwards the correct
  credential (SessionId vs SSO JWT) per backend". So credentials are
  construction-time: each adapter is built with `(transport, FinXCredentials)`
  where `FinXCredentials{session_id, sso_jwt}`. `.NET`/COTI use the `SessionId`
  already present in their request models for the header (must match the body
  value); Go-list / MIS / MF / brokerage / COTI-`ssotoken` read the credential
  the model does not carry.
- **Auth 401 → raise.** In-band business failures (HTTP 200) are returned as
  typed `ParsedEnvelope`; HTTP 401 raises `FinXAuthError`. Detection is by HTTP
  status (per the frozen parsers' `http_status=401` path), never body shape.
- **Magic bytes come from the FROZEN `ByteValidation`** in
  `app/contracts/flow.py`: `pdf_magic=b"%PDF"`, `excel_magic=b"PK"` (NOT the
  proposal-prose `PK\x03\x04`), `min_bytes=1024`. Frozen config wins.
- **`fetch_report_bytes(url, *, expected_format: ReportFormat) -> bytes`** —
  exact frozen-contract signature; creates its own httpx client (respx
  intercepts at transport level), validates, returns bytes.

---

## Task 1 — Package scaffold: errors, credentials, shared HTTP transport base

Files: `app/finx/adapters/__init__.py`, `errors.py`, `credentials.py`, `base.py`.

- `errors.py`: `FinXError` (base) + `FinXAuthError`, `FinXTimeoutError`,
  `FinXFetchError`, `FinXTransportError`.
- `credentials.py`: `FinXCredentials{session_id: str, sso_jwt: str | None}`.
- `base.py`: `TransportSettings` (module-local connect/read timeouts,
  `max_retries=1`, defaults) + `HttpTransport` wrapping an
  `httpx.AsyncClient`, with `post_json` / `post_bytes` returning
  `(status_code, body)` and applying the timeout+one-retry policy:
  timeout/network → `FinXTimeoutError`; 5xx after retry → `FinXTransportError`;
  in-band business failures (HTTP 200) are NEVER retried; logging emits endpoint
  name + HTTP status + latency only — never URL/`file_id`/`SessionId`/JWT/PII.

**Done:** `from app.finx.adapters import errors` imports; the four raised types
are distinct `Exception` subclasses of `FinXError`; a transient transport error
triggers exactly one retry then raises `FinXTimeoutError`; a persistent 5xx
raises `FinXTransportError`; the transport logs never contain a secret substring
(asserted in tests via a capturing handler). testCommand green for
`tests/finx_adapters/test_base.py` + `test_errors.py`.

## Task 2 — Byte-fetch helper + shared validation primitive

Files: `app/finx/adapters/fetch.py`.

- `fetch_report_bytes(url, *, expected_format)`: server-side GET, timeout+retry,
  then the shared validation primitive; raises `FinXFetchError` on
  short/empty/wrong-magic, `FinXTimeoutError` on network/timeout.
- `_validate_report_bytes(data, expected_format)`: size floor + magic bytes from
  the frozen `ByteValidation` (`ReportFormat.pdf → %PDF`, `ReportFormat.excel →
  PK`). Reused verbatim by the Go per-note download path.

**Done:** accepts `%PDF`/`PK` payloads ≥ `min_bytes`; raises `FinXFetchError` on
empty, below-floor, and wrong-magic bytes; raises `FinXTimeoutError` on
network/timeout; never logs the URL. testCommand green for `test_fetch.py`.

## Task 3 — `.NET` middleware adapter (6 endpoints)

Files: `app/finx/adapters/dotnet.py`.

- `DotNetMiddlewareAdapterImpl` satisfying `DotNetMiddlewareAdapter`:
  `get_global_pnl_pdf`, `get_ledger_details_pdf`, `get_tax_report_pdf`,
  `get_global_pnl_new`, `get_detailed_pnl`, `get_ledger_details`.
- URL from `ENDPOINTS[...]` host+path; header `authorization: <req.SessionId>`;
  body = `req.model_dump()` (PascalCase, `SessionId` duplicated in body);
  `parse_dotnet_envelope(body, http_status=status)`; `auth_error` outcome →
  raise `FinXAuthError`; no-data/error returned as typed `ParsedEnvelope`.

**Done:** `isinstance(impl, DotNetMiddlewareAdapter)`; each endpoint POSTs to its
correct `finx.choiceindia.com/api/middleware/...` URL with the SessionId header
AND SessionId in body; success/no-data/error/401 outcomes correct against the
`.NET` fixtures (`pnl_download_success`, `pnl_email_success`, `pnl_no_data`,
`ledger_pdf_success`, `tax_failure`, `global_pnl_new_object`,
`global_pnl_new_falsy_array`, `ledger_details_success`, `ledger_no_data`,
`detailed_pnl_success`, `dotnet_401`); `GetGlobalPNLNew` sends `With_Exp` truthy;
`GetDetailedPNL` sends `UserId="neuron"`; `GetLedgerDetails` sends
`LoginId="JIFFY"`/`Group="Group1"`. testCommand green for `test_dotnet.py`.

## Task 4 — Go middleware adapter (contract list, per-note download, brokerage)

Files: `app/finx/adapters/go.py`.

- `list_contract_notes`: `finx.` host, header `authorization: <session_id>` ONLY
  (no body `SessionId`); body snake_case = `req.model_dump()`;
  `parse_go_envelope`; `StatusCode 204 + Body {}` → no-data.
- `download_contract_note`: `api.` host, header `authorization: Session
  <session_id>`; returns raw PDF bytes through `_validate_report_bytes(...,
  ReportFormat.pdf)`; 401 → `FinXAuthError`.
- `get_brokerage_slab`: `api.` host, header `authorization: <sso_jwt>`; hybrid
  envelope parsed via `parse_dotnet_envelope` (keyed on `Status`, redundant
  `StatusCode` ignored); `Response` array returned verbatim.

**Done:** `isinstance(impl, GoMiddlewareAdapter)`; hosts/headers exactly as
above; `contract_note_list_success` keyed by `file_id` (never `id`);
`contract_note_204_no_data` → no-data; brokerage `brokerage_hybrid_success`
parses to a success envelope whose payload is the raw group array (no rupee
computation); download validates bytes and never logs `file_id`. testCommand
green for `test_go.py`.

## Task 5 — MIS reports adapter (CML)

Files: `app/finx/adapters/mis.py`.

- `generate_report`: camelCase body `{reportType, searchBy, searchValue}`;
  headers `authType: jwt` + `authorization: <sso_jwt>` + `source: FINX_ANDROID`;
  `parse_mis_envelope`; 401 (HTTP) → `FinXAuthError`; success payload carries
  `body.cmlLink`.

**Done:** `isinstance(impl, MisReportsAdapter)`; the three MIS headers present;
CML never handed the SessionId; `cml_success` → success with `cmlLink` in
payload; `cml_401` served with HTTP 401 → `FinXAuthError`. testCommand green for
`test_mis.py`.

## Task 6 — MF profile adapter (Phase-2 greeting, HEAVY PII)

Files: `app/finx/adapters/mf.py`.

- `get_profile_extended`: header `authorization: <sso_jwt>`; body `{InvCode}`;
  `parse_dotnet_envelope`; on success the payload is REDUCED to the first name
  only (`GetProfileResponse.first_name()`) — the heavy-PII profile object never
  becomes the payload, is never logged, stored, or traced.

**Done:** `isinstance(impl, MfProfileAdapter)`; success `ParsedEnvelope.payload`
is a first-name string, not the profile object; no PAN/email/mobile/DOB/bank
value appears in the returned envelope or any log. testCommand green for
`test_mf.py`.

## Task 7 — COTI (finxomne) holdings adapter

Files: `app/finx/adapters/coti.py`.

- `get_holdings`: header `authorization: Session <req.SessionId>` + `ssotoken:
  <sso_jwt>`; body = `req.model_dump()` (includes `GroupId="HO"`, `UserCode`,
  `UserId`, `SessionId`, `Status`, caller-supplied `accessToken` FINX JWT);
  `parse_dotnet_envelope`. Transport-complete though the flow is BLOCKED; the
  adapter does not source the FINX JWT (caller-supplied via the request model).

**Done:** `isinstance(impl, FinxOmneCotiAdapter)`; all three credentials wired
(Session-prefixed header, ssotoken header, body accessToken); parses via the
dotnet parser; the FINX JWT is never logged. testCommand green for
`test_coti.py`.

## Task 8 — Facade + package exports

Files: `app/finx/adapters/facade.py`, update `app/finx/adapters/__init__.py`.

- `FinXClientImpl(transport-or-client, credentials)` exposing `dotnet`, `go`,
  `mis`, `mf`, `coti` — satisfies the frozen `FinXClient` Protocol.
- `__init__.py` exports: the five adapter impls, `FinXClientImpl`,
  `FinXCredentials`, `fetch_report_bytes`, and the four error types.

**Done:** `isinstance(FinXClientImpl(...), FinXClient)`; the five attributes each
satisfy their per-backend Protocol; public names importable from
`app.finx.adapters`. testCommand green for `test_facade.py`.

## Task 9 — Consolidated logging-discipline + no-leak assertions

Files: `tests/finx_adapters/test_redaction.py` (+ any gaps found).

- Assert across all adapters and `fetch_report_bytes`: no report URL, `file_id`,
  signed query string, `SessionId`, JWT, `cmlLink`, or PII substring reaches any
  log sink; the FinX `Reason` MAY appear in the server-side log but never in a
  returned client-visible field beyond `ParsedEnvelope.reason`.

**Done:** the full `pytest tests/finx_adapters/` is green and the doneCondition
holds: five adapters implement their frozen methods; every endpoint is
request-assembled per its traps and parsed via the correct frozen parser; `.NET`
and MIS 401 → `FinXAuthError`; timeouts → `FinXTimeoutError`; `fetch_report_bytes`
accepts `%PDF`/`PK` ≥ floor and raises `FinXFetchError` on short/empty/wrong
magic; no test asserts a URL/`file_id`/`Reason` reaching a client-visible sink.
