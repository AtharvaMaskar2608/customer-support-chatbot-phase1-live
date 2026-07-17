## ADDED Requirements

### Requirement: Per-backend adapter set for five hosts

The system SHALL define a `FinXClient` facade Protocol plus five per-backend
adapter Protocols, NOT one generic wrapper. Each adapter SHALL own its host,
casing convention, response envelope, and credential scheme:

- `DotNetMiddlewareAdapter` — `finx.choiceindia.com/api/middleware`; PascalCase;
  `{Status, Response, Reason}`; auth = `authorization: <SessionId>` header **and**
  `SessionId` duplicated in the JSON body.
- `GoMiddlewareAdapter` — `finx.` and `api.choiceindia.com/middleware-go`;
  snake_case; `{StatusCode, Message, DevMessage, Body}`; auth = `authorization`
  header only for the contract list (`Session `-prefixed on the `api.` per-note
  download; `get-brokerage-slab` on `api.` uses the SSO JWT).
- `MisReportsAdapter` — `finx.choiceindia.com/mis/reports`; camelCase;
  `{statusCode, message, devMessage, body}`; auth = `authType: jwt` +
  `authorization: <SSO JWT>` + `source: FINX_ANDROID`.
- `MfProfileAdapter` — `mf.choiceindia.com/api/v2/investor/profile`; auth =
  `authorization: <SSO JWT>`.
- `FinxOmneCotiAdapter` — `finxomne.choiceindia.com/COTI/V1`; auth =
  `authorization: Session <SessionId>` + `ssotoken: <SSO JWT>` header + a
  FINX-issued JWT in the body `accessToken`.

The system SHALL route each endpoint to the adapter that owns its backend, and
SHALL forward the correct credential (SessionId vs SSO JWT) per backend.

#### Scenario: CML uses the SSO JWT, not the SessionId

- **WHEN** the client generates a CML report
- **THEN** it SHALL call `MisReportsAdapter` with the SSO JWT (`accessToken`), and SHALL NOT pass the SessionId to that backend

#### Scenario: DotNet endpoints duplicate SessionId into the body

- **WHEN** the client calls any `/api/middleware` endpoint
- **THEN** the request SHALL carry the SessionId both in the `authorization` header and as `SessionId` in the JSON body; `/middleware-go` requests SHALL NOT include `SessionId` in the body

### Requirement: Three response-envelope parsers

The system SHALL provide exactly three envelope parsers, each returning a
normalized result with an outcome (`success` / `no_data` / `auth_error` /
`error`), the payload, and the server `reason`:

- `parse_dotnet_envelope` for `{Status, Response, Reason}` — success when
  `Status == "Success"`; no-data when `Status == "Fail"` and the `Reason` is a
  no-data reason. `Response` SHALL be treated as polymorphic (URL string,
  confirmation string, array, object, or null).
- `parse_go_envelope` for `{StatusCode, Message, DevMessage, Body}` — success
  when `StatusCode == 200`; no-data when `StatusCode == 204` with `Body == {}`.
- `parse_mis_envelope` for camelCase `{statusCode, message, devMessage, body}`
  — success when `statusCode == 200`.

The system SHALL NOT build a single generic parser. The system SHALL NOT
distinguish no-data by matching a single literal `Reason` string, because the
wording differs per endpoint ("Data not found." vs "Data not available.").
`parse_dotnet_envelope` SHALL tolerate **extra keys** (ignoring a redundant
`StatusCode`) rather than exact-shape-reject, so it also serves the brokerage
hybrid envelope, the `mf.` profile, and COTI Holdings. It SHALL treat `Response`
as string / array / object / null / **empty string** — the `.NET` 401 auth body
uses `Response: ""` (empty string, not null), so models SHALL NOT assume `Response`
is `str | null` only.

#### Scenario: No-data is reason-set based, not literal

- **WHEN** a `/api/middleware` response has `Status: "Fail"` with `Reason` "Data not available."
- **THEN** `parse_dotnet_envelope` SHALL classify the outcome as `no_data`, the same as it would for "Data not found."

#### Scenario: Brokerage hybrid envelope parsed on Status

- **WHEN** the brokerage response carries both `StatusCode` and `Status` (hybrid envelope)
- **THEN** `parse_dotnet_envelope` SHALL ignore the redundant `StatusCode`, key on `Status == "Success"`, and expose the `Response` array of segment groups intact

#### Scenario: Empty-string Response tolerated

- **WHEN** a `.NET` 401 auth body carries `Response: ""`
- **THEN** the parser and response models SHALL accept the empty string (not assume `Response` is `str | null` only)

### Requirement: Auth-failure detection by HTTP status

The system SHALL detect authentication failure by the transport HTTP status code
(`401`), before envelope parsing, because auth failures do not follow the in-band
`200`-with-Fail convention. The system SHALL tolerate the two differing 401
envelope shapes (`.NET` `{"Status":"Fail","Response":"","Reason":"Invalid
SessionId"}` vs MIS `{"statusCode":401,...}`). All other outcomes SHALL be
branched on the body envelope, never on HTTP status.

#### Scenario: 401 is an auth error regardless of body shape

- **WHEN** any FinX call returns HTTP 401
- **THEN** the client SHALL classify it as an auth error even though the `.NET` and MIS 401 bodies differ

#### Scenario: Business failures return HTTP 200

- **WHEN** a call returns HTTP 200 with a `Fail`/`204` body
- **THEN** the client SHALL branch on the body envelope, not the HTTP status

### Requirement: Per-endpoint identity-field and enum traps

The system SHALL pin the inconsistent per-endpoint identity fields and enum
semantics as typed request models, matching the 2026-07-16 captures:

- `GetLedgerDetails` (data) → `LoginId = "JIFFY"`, `Group = "Group1"`.
- `GetLedgerDetailsPDF` (file) → `LoginId = <client code>`, `Group = "GROUP1"`
  (uppercase), plus `Margin` (`0` normal; `1` = MTF [CONFIRM]).
- `GetGlobalPNLNew` / `GetGlobalPNLPDF` → `UserId = <client code>`; PNL data uses
  `With_Exp` int, PNL PDF uses `With_Exp` boolean.
- `GetDetailedPNL` → `UserId = "neuron"` (fixed literal).
- Contract Notes → `client_id` (list) / `client_code` (download).
- `RequestFor` SHALL be pinned per endpoint, NOT centralized: `GetGlobalPNLPDF`
  and `GetLedgerDetailsPDF` use `0`=download; `GetTaxReportPDF` uses `2`=download;
  all three use `1`=email. `FileFormat` `1`=PDF, `2`=Excel (Tax only).

#### Scenario: Ledger PDF identity differs from ledger data

- **WHEN** the client builds a `GetLedgerDetailsPDF` request
- **THEN** `LoginId` SHALL be the client code and `Group` SHALL be `"GROUP1"`, distinct from the data endpoint's `LoginId = "JIFFY"` / `Group = "Group1"`

#### Scenario: RequestFor download value forks by endpoint

- **WHEN** the client requests a download from `GetGlobalPNLPDF` versus `GetTaxReportPDF`
- **THEN** `RequestFor` SHALL be `0` for the PNL PDF and `2` for the Tax PDF, with `1` meaning email on both

### Requirement: Typed request/response models per captured endpoint

The system SHALL define typed request and response models for each captured
endpoint: P&L PDF, Ledger PDF, Tax Report PDF, Contract-Note list, Contract-Note
per-note download (raw PDF bytes), CML, Brokerage slab, Holdings, get-profile,
and the three fallback data endpoints (`GetGlobalPNLNew`, `GetDetailedPNL`,
`GetLedgerDetails`). Unverified fields SHALL be marked `[CONFIRM]`; uncaptured
shapes SHALL be marked `[GAP]`, matching `03_finx_api_reference.md`.

#### Scenario: Polymorphic PNL response modeled

- **WHEN** a `GetGlobalPNLPDF` response is parsed
- **THEN** the model SHALL represent `Response` as either a report URL string (download) or an email-confirmation string (email), and the email confirmation's registered-email leak SHALL be masked before any display

#### Scenario: With_Exp shape switch documented

- **WHEN** the client models `GetGlobalPNLNew`
- **THEN** the model SHALL record that a truthy `With_Exp` yields a `{Trades, Expenses}` object and a falsy value yields a bare array, and the contract SHALL require sending `With_Exp` truthy for a stable object shape

#### Scenario: Contract-note rows keyed by file_id

- **WHEN** the client models the contract-note list `Body.contractNotes` entries
- **THEN** each entry SHALL expose `date` (DDMMYYYY), `file_id`, `group` (matched case-insensitively), `invoice_number`, and the model SHALL key rows by `file_id`, never by `id` (which duplicates `date`)

### Requirement: Sensitive values never leave the backend

The system SHALL treat report URLs, `file_id` values, the CML `cmlLink` signed
URL, server filenames, and the raw registered email as sensitive. These SHALL be
fetched server-side and SHALL NOT be returned to the client, logged, or serialized
into any render block. The backend SHALL gate `client_id`/`client_code` by the
authenticated widget session and SHALL NOT proxy a user-supplied client identifier
(the Go contract-note endpoints enforce no auth). The CML 120-second signed-URL
expiry SHALL NOT be relied on as a security boundary.

#### Scenario: Contract-note client id is session-gated

- **WHEN** the client queries or downloads a contract note
- **THEN** the `client_id`/`client_code` SHALL be taken from the authenticated session, never from user input, and the `file_id` SHALL NOT appear in client-visible output or logs

#### Scenario: CML link is fetched server-side and discarded

- **WHEN** CML generation returns a `body.cmlLink` signed URL
- **THEN** the backend SHALL fetch the bytes server-side and SHALL NOT surface, cache, or log the URL, and SHALL NOT rely on the 120-second expiry as protection

### Requirement: Capture fixtures back the parser tests

The system SHALL store the sanitized 2026-07-16 capture JSON as test fixtures and
use them as parser/model test data. Fixtures SHALL cover: PNL download success,
PNL email success, PNL no-data failure, Ledger PDF success, Ledger no-data
failure, CML success (camelCase `body.cmlLink`), CML 401, contract-note list
success, contract-note 204 no-data, Tax failure ("Data not available."),
brokerage hybrid success, `.NET` 401, MIS 401, `GetGlobalPNLNew` success
(`{Trades, Expenses}`), `GetGlobalPNLNew` falsy-`With_Exp` bare array,
`GetDetailedPNL` success array, and `GetLedgerDetails` success array. Fixtures
SHALL carry no real SessionIds, JWTs, Client IDs, or registered emails.

#### Scenario: Each parser branch has a fixture

- **WHEN** the parser test suite runs
- **THEN** every parser outcome (`success` / `no_data` / `auth_error`) SHALL be exercised by at least one sanitized capture fixture

#### Scenario: Fixtures are sanitized

- **WHEN** a capture fixture is stored under `tests/fixtures/finx/`
- **THEN** SessionIds, JWTs, Client IDs, and registered emails SHALL be replaced with placeholders while field names, casing, and value types remain verbatim
