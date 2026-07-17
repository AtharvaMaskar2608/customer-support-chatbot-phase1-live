# Proposal: finx-http-adapters

## Why

`contracts-foundation` freezes the `FinXClient` interface, the three envelope
parsers, the typed request/response models, and the capture fixtures — but no
code actually talks to FinX yet. Every report flow (`flow-pnl`, `flow-ledger-mtf`,
`flow-contract-notes`, `flow-tax-report`, `flow-cml`, `flow-brokerage`) needs a
working transport layer before it can be built, and the FinX surface is not one
backend but **five hosts with five auth schemes and mutually incompatible
casing/envelope conventions** (`02_technical_spec.md` §9; `03_finx_api_reference.md`
§1). A single generic HTTP wrapper is explicitly ruled out (§4.8 trap 2, §1
"per-backend adapter set"). This change implements the per-backend adapters
behind the frozen interfaces so the flow tasks can fan out against a real
transport instead of stubbing HTTP themselves and colliding on `app/finx/`.

It also owns the two cross-cutting transport concerns that must be implemented
exactly once: (1) **auth-failure detection** — HTTP `401` with per-backend
envelope shapes that differ (`03` §7 table), distinct from in-band business
failures which are HTTP `200` + `Status: "Fail"`; and (2) the **server-side
byte-fetch helper** that fetches a FinX-issued (often unauthenticated) report
URL, validates it (size floor + magic bytes), and returns raw bytes — so the
URL and `file_id` handles never reach the client or logs (`02` §2.6; `03` §5
trap 8, §7 FLAG A/B).

## What Changes

Everything here is **transport implementation** behind already-frozen
interfaces — no flow logic, no router, no rendering, no new contracts. The
adapters import the interfaces/parsers/models/fixtures from `contracts-foundation`
and implement them.

- **Five per-backend adapters**, one per host/auth/envelope family:
  1. `.NET` `/api/middleware` (finx. host) — PascalCase, `{Status,Response,Reason}`,
     auth = `authorization: <SessionId>` header **+ `SessionId` duplicated in body**.
     Wraps `GetGlobalPNLPDF`, `GetLedgerDetailsPDF`, `GetTaxReportPDF` (file/email),
     plus the fallback data endpoints `GetGlobalPNLNew`, `GetLedgerDetails`,
     `GetDetailedPNL` (no-data / empty-range detection only).
  2. Go `/middleware-go` (finx. **and** api. hosts) — snake_case body, **no
     `SessionId` in body**, `{StatusCode,Message,DevMessage,Body}`. Wraps the
     Contract Note list (finx., `authorization: <SessionId>`), the per-note
     download (api., `authorization: Session <SessionId>` prefix, **returns raw
     PDF bytes**), and Brokerage (api., **JWT auth**, **hybrid envelope**).
  3. MIS `/mis/reports/generate` — camelCase `{statusCode,message,devMessage,body}`,
     auth = `authType: jwt` + `authorization: <SSO JWT>` + `source: FINX_ANDROID`.
     Wraps CML.
  4. `mf.` profile (`mf.choiceindia.com`) — `{Status,Response,Reason}`, **JWT auth
     (SSO accessToken, not SessionId)**. Wraps get-profile; the adapter method
     **extracts only the first name** from `FirstHolderName` and returns that —
     the heavy-PII profile object never leaves the transport boundary (`03` §4.6b).
  5. `finxomne. /COTI` (`finxomne.choiceindia.com/COTI/V1/…`) — `{Status,Response,Reason}`,
     **three credentials at once**: `authorization: Session <SessionId>` +
     `ssotoken: <SSO JWT>` header + a FINX-issued JWT as body `accessToken`.
     Wraps Holdings.
- **Per-endpoint request assembly** honouring every field-level trap (`03` §5):
  per-endpoint `RequestFor` (0/1 on PNL/Ledger PDF, 2/1 on Tax — never
  centralized), per-endpoint identity field (`LoginId="JIFFY"` vs `<client code>`
  vs `UserId="neuron"`), `Group` casing (`GROUP1` vs `Group1` vs `Cash/Derv/Comm`),
  `With_Exp` sent truthy for a stable object shape, `Margin` per-call. Values come
  from the frozen request models; the adapter never invents them.
- **Envelope handling** via the three frozen parsers: `{Status,Response,Reason}`
  (used by `.NET`, `mf.`, COTI, and — ignoring the redundant `StatusCode` — the
  Brokerage hybrid), `{StatusCode,Message,DevMessage,Body}` (Go contract list),
  and the MIS camelCase parser (CML). In-band business failures (`Status:"Fail"`
  / `StatusCode:204`) are returned as typed results, never raised.
- **Timeout & retry policy** — bounded connect/read timeouts on every call;
  transport-transient failures (connection reset, DNS, 5xx) get at most one
  bounded retry; **timeouts and network failures raise a typed
  `FinXTimeoutError`** (mapped downstream to E-TIMEOUT by the engine). In-band
  business failures are **never** retried at this layer (the engine owns the
  re-generate-once policy). Timeout/retry values are adapter-module-local
  settings with sensible defaults (remote-tunability, if wanted, is a
  `contracts-foundation` follow-up — this change does not touch the frozen
  remote-config schema).
- **Auth-failure envelope handling per backend** (`03` §7): detect auth failure
  by **HTTP `401`, not body shape** — `.NET` returns
  `{"Status":"Fail","Response":"","Reason":"Invalid SessionId"}` + header
  `authstatus: Unauthorized` (note `Response` is `""`, not `null`); MIS returns
  `{"statusCode":401,"message":"Invalid Request.",...}` (no `authstatus`); the Go
  contract endpoint enforces **no** auth (FLAG A) so has no 401 path. All 401s
  raise a typed `FinXAuthError`; stale vs garbage SessionId are indistinguishable
  (documented, not a bug).
- **Server-side byte-fetch helper** — `fetch_report_bytes(url, *, expected_format)`:
  GETs the FinX report URL server-side (PNL/Ledger/Tax on
  `client-report.choiceindia.com/PDFReports/…`; CML on the CloudFront/S3
  pre-signed `onmedia.choiceindia.com` URL — **does not rely on the 120s /
  single-use signature as a boundary**, FLAG B), validates **size floor + magic
  bytes** (`%PDF` for PDF, `PK\x03\x04` for xlsx) against the frozen
  byte-validation config, and returns raw bytes; on validation/network/timeout
  failure raises a typed `FinXFetchError`/`FinXTimeoutError`. The Contract Note
  download path returns raw bytes directly from the POST and runs through the
  **same** magic-byte/size-floor validation primitive.
- **Logging discipline** — the adapters never emit report URLs, `file_id`s,
  signed query strings, `SessionId`, JWTs, or PII to any sink. The FinX `Reason`
  string **may** be logged to the server-side log for diagnostics (never to any
  client-visible surface); diagnostic logs carry endpoint name + HTTP status +
  latency only (`02` §2.6; `03` §5 trap 8, §7 FLAG A).
- **Client-id gating note** — per FLAG A the Contract Note endpoints authorize
  purely on the body `client_id`, so the adapters accept a `client_id` **only
  from the caller** (the session-bound value the orchestrator supplies) and never
  a user-typed one; ownership enforcement itself lives in the orchestrator/flow,
  not here — the adapter documents the invariant and refuses to log the value.

Tests are **fixture/`respx`-mock based** (`respx` is the repo-wide httpx mock,
declared by `contracts-foundation`) — every parser branch and error path is
exercised against the `tests/fixtures/finx/**` captures from `contracts-foundation`;
**no live FinX calls**.

## Capabilities

### New Capabilities

- `finx-http-adapters`: the concrete per-backend HTTP transport behind the frozen
  `FinXClient` interface — five host/auth/envelope adapters, per-endpoint request
  assembly, auth-failure and timeout handling, the server-side byte-fetch +
  magic-byte/size-floor validation primitive, and the logging-redaction discipline.

### Modified Capabilities

None — this implements the `finx-client` capability's interface without editing
its contract surface.

## Impact

- **New code**: `app/finx/adapters/**` (one module per backend + a shared HTTP
  base for timeout/retry/logging + the byte-fetch helper), and
  `tests/finx_adapters/**`.
- **APIs**: no new public API; realizes the frozen `FinXClient` methods. All FinX
  calls remain server-side only.
- **Downstream**: unblocks the six in-scope report flows (rows 6–11) and any
  caller that needs report bytes; the engine (`flow-engine-runtime`) imports the
  byte-fetch primitive.
- **Out of scope / deferred**: the `mf.` get-profile method is transport-complete
  but its consumer is Phase-2 (Phase 1 greets by Client ID); the COTI Holdings
  method is transport-complete but its flow is **BLOCKED** and its body FINX-JWT
  credential provenance is **[CONFIRM]** (`03` §4.6d) — the adapter takes that JWT
  as a caller-supplied parameter and does not attempt to source it. Global-Detail
  file delivery has **no endpoint [GAP]** (only `GetDetailedPNL` data), so no
  download adapter is provided for it.

## Files touched

Exactly the two directories assigned to row 1 of the ownership map:

- `app/finx/adapters/**` — the five adapters, shared HTTP base, byte-fetch helper.
- `tests/finx_adapters/**` — fixture/httpx-mock tests.

Untouched (imported read-only, not edited): `app/finx/interfaces.py`,
`app/finx/envelopes.py`, `app/finx/models.py`, `app/contracts/**`, `app/config/**`
(all owned by `contracts-foundation`). **Lockfiles, migrations, and root config
are not touched** — `contracts-foundation` declares all backend deps (`httpx`
included) up front.

## Contracts & API structure

Implements the `FinXClient` adapter methods declared in the frozen
`app/finx/interfaces.py`; request/response types are the frozen models in
`app/finx/models.py`; envelopes parsed by the frozen `app/finx/envelopes.py`.
Method names below are indicative and must bind to the frozen interface exactly.

**Cross-cutting transport contract**
- Business failures are **in-band** (HTTP 200, branch on `Status`/`StatusCode`) →
  returned as typed results (e.g. `Status:"Fail"` / `StatusCode:204` → a typed
  "no data" result the engine maps to `E-NODATA`). Never raised.
- `FinXAuthError` (HTTP 401), `FinXTimeoutError` (timeout/network), `FinXFetchError`
  (byte validation / URL fetch), `FinXTransportError` (unexpected 5xx/parse) are
  the raised types; the engine (`flow-engine-runtime`) maps them to the shared
  taxonomy (`E-TIMEOUT`/`E-FETCH`/`E-UNKNOWN`).
- `fetch_report_bytes(url: str, *, expected_format: ReportFormat) -> bytes` —
  server-side GET + size-floor + magic-byte validation; raises `FinXFetchError`
  on short/empty/wrong-magic bytes, `FinXTimeoutError` on network/timeout.

**Every endpoint the adapters wrap** (URL, casing, envelope, auth, markers — per `03`):

| # | Flow / purpose | Method + URL | Casing | Envelope | Auth scheme | Markers (per `03`) |
|---|---|---|---|---|---|---|
| 1 | P&L file/email | `POST finx.choiceindia.com/api/middleware/GetGlobalPNLPDF` | PascalCase | `{Status,Response,Reason}` | `authorization: <SessionId>` hdr **+ `SessionId` in body** | `RequestFor` 0=dl/1=email; `With_Exp: true` (bool); `Response` polymorphic (URL vs email confirmation — email **leaks uppercased registered email → mask** `san***@…`); no-data `Reason:"Data not found."` LIVE-CONFIRMED |
| 2 | Ledger/MTF file/email | `POST …/api/middleware/GetLedgerDetailsPDF` | PascalCase | `{Status,Response,Reason}` | `authorization: <SessionId>` hdr + body `SessionId` | `RequestFor` 0=dl, email `1` **[CONFIRM]**; `LoginId=<client code>`; `Group="GROUP1"`; `Margin` 0=normal, **`1`=MTF [CONFIRM]/[UNCONFIRMED]** (byte-identical on no-MTF acct); success URL LIVE-CONFIRMED |
| 3 | Tax / Capital Gain file/email | `POST …/api/middleware/GetTaxReportPDF` | PascalCase | `{Status,Response,Reason}` | `authorization: <SessionId>` hdr + body `SessionId` | `RequestFor` **2=dl**/1=email; `FileFormat` 1=PDF/2=Excel; `FinYear` `YYYY-YYYY`; `Response`=string URL (`.pdf` or `.xlsx`); failure `Reason:"Data not available."` (different wording — don't string-match) LIVE-CONFIRMED |
| 4 | P&L data (no-data detect / fallback) | `POST …/api/middleware/GetGlobalPNLNew` | PascalCase | `{Status,Response,Reason}` | `authorization: <SessionId>` hdr + body `SessionId` | `UserId=<client code>`; **`With_Exp` shape-switch** (truthy→`{Trades,Expenses}` object, falsy→bare array) — **send truthy**; accepts int & bool LIVE-CONFIRMED |
| 5 | Ledger data (fallback) | `POST …/api/middleware/GetLedgerDetails` | PascalCase | `{Status,Response,Reason}` | `authorization: <SessionId>` hdr + body `SessionId` | `LoginId="JIFFY"` (literal); `Group="Group1"`; `Response`=array; `Narration` **contains third-party PII** — never log LIVE-CONFIRMED |
| 6 | Detailed P&L data (Global Detail data side) | `POST …/api/middleware/GetDetailedPNL` | PascalCase | `{Status,Response,Reason}` | `authorization: <SessionId>` hdr + body `SessionId` | `UserId="neuron"` (literal); `Group` `Group1`/`Group23`; array. **No file/download endpoint [GAP]** — Global-Detail delivery BLOCKED |
| 7 | Contract Note list | `POST finx.choiceindia.com/middleware-go/report/contract` | snake_case | `{StatusCode,Message,DevMessage,Body}` | `authorization: <SessionId>` hdr only (**no body `SessionId`**) | **Mixed casing** (`contractNotes` camelCase, note fields snake_case); key rows by `file_id` (not `id`); `date`=`DDMMYYYY`; `group` match case-insensitively; 204+`Body:{}` empty. 🔴 **FLAG A: NO auth enforced — gate `client_id` server-side** LIVE-CAPTURED |
| 8 | Contract Note per-note download | `POST api.choiceindia.com/middleware-go/contract/download` | snake_case | **none — raw PDF bytes** | `authorization: Session <SessionId>` (**"Session " prefix**) | Different host (api.); returns `application/pdf` bytes directly (no URL/envelope); runs through `fetch`-side magic-byte/size validation. 🔴 **FLAG A extends: no auth enforced** LIVE-CAPTURED |
| 9 | Brokerage (card) | `POST api.choiceindia.com/middleware-go/v2/get-brokerage-slab` | PascalCase key `ClientID` | **hybrid** `{StatusCode, Status, Response, Reason}` → parse via `{Status,Response,Reason}` | **JWT (SSO accessToken)** hdr | `Response`=array of `{title, list:[{title,desc}]}`; **render `desc` verbatim, don't compute rupees**; **dynamic — no hardcoded segments/rows**; card only (no PDF/email) LIVE-CAPTURED |
| 10 | CML file | `POST /mis/reports/generate` | camelCase | `{statusCode,message,devMessage,body}` | `authType: jwt` + `authorization: <SSO JWT>` + `source: FINX_ANDROID` | Body `{reportType:"cml",searchBy:"client-id",searchValue}`; link at **`body.cmlLink`** (S3 SigV4 pre-signed, CloudFront); filename `Client_Master_List.pdf` (kept, not renamed). 🔴 **FLAG B: 120s/single-use is NOT a boundary**; 401 envelope `{"statusCode":401,"message":"Invalid Request."}` LIVE-CAPTURED |
| 11 | get-profile (Phase-2 greeting) | `POST mf.choiceindia.com/api/v2/investor/profile/extended` | PascalCase | `{Status,Response,Reason}` | **JWT (SSO accessToken)** hdr | Body `{InvCode}`. 🔴 **HEAVY PII** — adapter returns **only first name** from `FirstHolderName`; discards `PAN/Address/Email/Mobile/DOB/Bank[]/…`; never logs/stores/traces/returns the object. **Phase-2** consumer LIVE-CAPTURED |
| 12 | Holdings (card) | `POST finxomne.choiceindia.com/COTI/V1/Holdings` | PascalCase | `{Status,Response,Reason}` | `authorization: Session <SessionId>` + `ssotoken: <SSO JWT>` hdr + body `accessToken` (**FINX-issued JWT**) | Body `GroupId:"HO"`, `UserCode`/`UserId`, `SessionId`, `accessToken`; `Response.lDictHoldingData` **object keyed by ISIN** (iterate `.values()`); `LTP`/`CP` in **paise (÷100)**, `ABP`/`ASP` in rupees. 🔴 **Holding flow BLOCKED**; body FINX-JWT provenance **[CONFIRM]** (caller-supplied) LIVE-CAPTURED |

Byte-fetch targets (via `fetch_report_bytes`): `client-report.choiceindia.com/PDFReports/…`
(rows 1–3 URLs) and `onmedia.choiceindia.com` (row 10 CML). Row 8 returns bytes
directly (no fetch step). Magic bytes: PDF `%PDF`, xlsx `PK\x03\x04`.

## Dependencies & contracts consumed

**Consumes (frozen, imported read-only) from `contracts-foundation` (change 0):**
- `app/finx/interfaces.py` — the `FinXClient` adapter interface set this change realizes.
- `app/finx/envelopes.py` — the three envelope parsers.
- `app/finx/models.py` — typed per-endpoint request/response models.
- `app/contracts/**` — the `ReportFormat`/byte-validation config (magic bytes,
  size floor) and shared error-type surface.
- `app/config/**` — host base URLs / `from:` build-tag value if centralized there.
- `tests/fixtures/finx/**` — the 2026-07-16 capture fixtures used as test data.
- `pyproject.toml` + lockfile — declares `httpx` (transport) and `respx` (the
  repo-wide httpx mock, in the dev/eval extras group); this change adds no deps.

**Must land first:** change 0 (`contracts-foundation`) — hard gate; the
interfaces/parsers/models/fixtures must exist in main.
**Can proceed in parallel with:** all flow changes (6–11) build against these
adapters but each owns a disjoint `app/flows/<name>.py`; `flow-engine-runtime`
(2) imports only the byte-fetch primitive. No file overlap with any other change.

## Done condition & test command

Done when: all five adapters implement their frozen interface methods; every
endpoint in the table above is request-assembled per its traps and parsed via the
correct envelope; the `401` auth-failure path raises `FinXAuthError` for `.NET`
and MIS envelopes; timeouts raise `FinXTimeoutError`; `fetch_report_bytes`
accepts valid `%PDF`/`PK` bytes above the size floor and raises `FinXFetchError`
on short/empty/wrong-magic bytes; and no test asserts a URL/`file_id`/`Reason`
reaching a client-visible sink. All fixture/mock-based, no live calls.

Test command: `pytest tests/finx_adapters/` — green (`respx` httpx mock + the
`tests/fixtures/finx/**` captures; zero network).
