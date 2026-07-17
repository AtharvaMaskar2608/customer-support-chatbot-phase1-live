# FinX API Reference — Reconciled (Phase 1)

> **Status: authoritative working reference.** Reconciles the originally
> documented data APIs (`docs/finx_api_reports_documentation.md`) with the
> **2026-07-16 live captures** (PDF/email report endpoints + CML) and the
> Android app enums. This is the detailed reference cited from
> `02_technical_spec.md` §4. Where a capture and the old doc disagree, the
> reconciled position here wins; unresolved items are tagged **[CONFIRM]** /
> **[GAP]**.

## 0. How to read this doc

- **[DATA]** — documented endpoint that returns report *data* (JSON records).
- **[FILE]** — endpoint that generates a file and returns a **download URL** or
  **emails** it. These are the newly captured `*PDF` / `/mis` endpoints and are
  the ones the report flows actually use (owner decision: the data APIs don't
  support both PDF-download AND email).
- **[GAP]** — no endpoint captured, or response schema still unknown.
- **[CONFIRM]** — value/behaviour inferred from one capture or by analogy; needs
  one more capture to lock.

---

## 1. Backends & authentication — there are now THREE

| Backend | Base | Casing | Envelope | Auth |
|---|---|---|---|---|
| Legacy middleware | `/api/middleware` | PascalCase | `{Status, Response, Reason}` | `authorization: <SessionId>` header **+ `SessionId` in body** |
| Go middleware | `/middleware-go` | snake_case | `{StatusCode, Message, DevMessage, Body}` | `authorization: <SessionId>` header only |
| **MIS reports (NEW)** | `/mis/reports` | camelCase | unknown **[GAP]** | `authType: jwt` + `authorization: <SSO JWT>` + `source: FINX_ANDROID` |

**Critical auth split:** the MIS backend (used by CML) authenticates with the
**SSO JWT** — i.e. the `accessToken` query param the frontend hands off
(`iss: https://sso.choiceindia.com`), **not** the SessionId. The two middleware
backends use the SessionId. The integration must route the right credential to
the right backend: **CML fails if handed the SessionId.** The widget must
therefore capture and forward BOTH `sessionId` and `accessToken`.

- Errors are **in-band for business failures** (e.g. "Data not found"): HTTP
  `200`, branch on `Status`/`StatusCode` in the body. **Exception (live-tested
  2026-07-16): auth failures return a real HTTP `401`** with response header
  `authstatus: Unauthorized` and body
  `{"Status":"Fail","Response":"","Reason":"Invalid SessionId"}` — note the
  error text lives in `Reason` (not `Message`), and `Response` is an empty
  string, not null. Client code must handle both patterns.
- 🔑 **"Invalid SessionId" means a session↔client MISMATCH, not necessarily an
  expired token** (learned the hard way 2026-07-16). The `.NET` backend binds a
  SessionId to one ClientId; calling `GetLedgerDetails` etc. with a *different*
  ClientId than the session owns returns the same `401 Invalid SessionId`. A
  valid session for client `X008593` returned `401` for `X04883` and `200` for
  `X008593`. **Implication**: always send the ClientId that the widget's
  session actually belongs to; never mix. (This is also a *good* security
  property — the `.NET` backend enforces session-client binding, unlike the Go
  contract endpoint — see §7 FLAG A.)
- **No login/refresh endpoint documented** — SessionId acquisition still
  undocumented; the widget receives it from the app handoff. Lifetime/expiry
  not yet measured (the one test token stayed valid across the whole session).
- `from:` header is a **client-build tag, NOT auth and NOT a source router**
  (live-tested 2026-07-16). The same session+client returned `200` with the
  web tag, the android tag, a made-up `Jini_backend_v1` tag, AND with no
  `from:` header at all. **Conclusion: one API surface serves both web and
  android — do NOT build source-specific endpoints.** The Jini backend can
  send any stable `from:` value. (Only possible exception: the MIS/CML backend,
  whose JWT carries `source: FINX_ANDROID` — source-gating there is
  unconfirmed [CONFIRM].) What actually varies by platform is the SessionId
  (minted per login), not the endpoint; the ClientId identifies the account,
  not the source.

---

## 2. Enum reconciliation — `RequestFor` is NOT global

Android app enums (authoritative where they apply):

- **ViewType**: `Mail = 1`, `Download = 2`
- **FileFormatType**: `Pdf = 1`, `Excel = 2`

Observed `RequestFor` usage per endpoint:

| Endpoint | Download | Email | Matches ViewType? |
|---|---|---|---|
| `GetGlobalPNLPDF` | `0` | `1` | No (download is 0, not 2) |
| `GetLedgerDetailsPDF` | `0` | `1` **[CONFIRM]** | No (download is 0) |
| `GetTaxReportPDF` | `2` | `1` | **Yes** (Mail=1, Download=2) |

**Rule: `RequestFor = 1` = Email/Mail is the only value consistent across all
three.** The download value forks — Tax uses `2` (ViewType-compliant), while
PNL-PDF and Ledger-PDF use `0`. **Do NOT centralize `RequestFor` behind one
shared enum constant; hardcode it per endpoint.** `FileFormat` (1=PDF, 2=Excel)
is consistent wherever it appears (Tax only, so far).

---

## 3. Flow → endpoint map (the 11)

> **DECISION (2026-07-16): standardize on FILE delivery.** Every report is
> delivered as a downloadable file card — the goal is a document, not
> in-chat data points. So the flows call the **[FILE] endpoints** (the
> `*PDF` / contract-download / CML endpoints, captured from the android app
> but source-agnostic). The [DATA] endpoints (`GetLedgerDetails`,
> `GetGlobalPNLNew`, `GetDetailedPNL`) are **fallback only** — kept for
> empty-range detection *if* the file endpoints don't signal no-data cleanly
> (open question, under test). Not "android vs web APIs" — same endpoints from
> any source; we're choosing file-generating endpoints over data-returning
> ones.

Legend: bucket + endpoint. "Data API" columns list the documented endpoint kept
for reference/no-data detection even when a [FILE] endpoint drives delivery.

| # | Flow | Delivery endpoint | Data/list endpoint | Notes |
|---|---|---|---|---|
| 1 | Ledger | `GetLedgerDetailsPDF` [FILE] | `GetLedgerDetails` [DATA] | PDF endpoint likely supersedes the data→download two-step |
| 2 | MTF Ledger | `GetLedgerDetailsPDF` + `Margin:1`? [FILE][UNCONFIRMED] | `GetLedgerDetails` [DATA] | `Margin:0`/`:1` identical on test acct — MTF discriminator unverified |
| 3 | P&L (Equity/F&O/Comm) | `GetGlobalPNLPDF` [FILE] | `GetGlobalPNLNew` [DATA] | PDF endpoint ≠ the data endpoint |
| 4 | Detailed P&L / Global Detail | — **[GAP]** | `GetDetailedPNL` [DATA] | no file endpoint captured |
| 5 | Contract Notes | per-note download **[GAP]** | `/middleware-go/report/contract` [DATA/list] | list Body is `file_id`-keyed (§4.6) |
| 6 | Tax / Capital Gain | `GetTaxReportPDF` [FILE] | — | no separate CG API |
| 7 | Brokerage | `api.choiceindia.com/middleware-go/v2/get-brokerage-slab` [DATA/card] | — | JWT auth; dynamic slab list, card only (§4.6c) |
| 8 | CML | `/mis/reports/generate` [FILE] | — | JWT auth; response **[GAP]** |
| 9 | Holding | `finxomne.choiceindia.com/COTI/V1/Holdings` [DATA/card] | — | 3-credential auth; live data, no PDF leg captured (§4.6d) |
| 10 | get-profile | — | — **[GAP]** | supporting API; powers greeting |
| 11 | Freshdesk ticket | — | — **[GAP]** | supporting API; fields TBD |

---

## 4. Endpoint contracts

### 4.1 `POST /api/middleware/GetGlobalPNLPDF` — P&L file/email [FILE] (NEW)

```http
authorization: <SessionId>
from: android_9.2.1.260709
content-type: application/json
```
```json
{
  "ClientId": "X04883",
  "UserId": "X04883",
  "Group": "Cash",
  "FromDate": "2026-04-01",
  "ToDate": "2026-07-21",
  "RequestFor": 0,
  "With_Exp": true,
  "SessionId": "<SessionId>"
}
```

- `Group`: `Cash` (Equity) / `Derv` (F&O) / `Comm` (Commodity) — never show
  "Derv" to a customer.
- `UserId` = `ClientId`.
- `RequestFor`: `0` = download (URL) · `1` = email.
- `With_Exp`: **boolean `true`** here (the data API `GetGlobalPNLNew` uses int
  `1` — send the correct type per endpoint).
- No `FileFormat` field → **PDF only** (matches flow: P&L offers PDF + email, no
  Excel).

**Response — download (`RequestFor:0`):**
```json
{ "Status": "Success",
  "Response": "https://client-report.choiceindia.com/PDFReports/PNLReport_<id>_<ClientId>.pdf",
  "Reason": "" }
```
**Response — email (`RequestFor:1`):**
```json
{ "Status": "Success",
  "Response": "PnL Report mail sent successfully to <REGISTERED_EMAIL, UPPERCASED>",
  "Reason": "" }
```

⚠️ `Response` is **polymorphic** (URL string vs human-readable confirmation).
The email confirmation **leaks the full registered email** (uppercased) — mask
before display (`san***.harsha@gmail.com`).

**Failure — no data (LIVE-CONFIRMED 2026-07-16):**
```json
{ "Status": "Fail", "Response": null, "Reason": "Data not found." }
```
(HTTP 200; distinct from the auth-layer 401 in §1.)

### 4.2 `POST /api/middleware/GetLedgerDetailsPDF` — Ledger/MTF file/email [FILE] (NEW)

```http
Authorization: <SessionId>
from: android_9.2.2.260710
```
```json
{
  "ClientId": "X04883",
  "LoginId": "X04883",
  "Group": "GROUP1",
  "Margin": 0,
  "FromDate": "2026-07-01",
  "ToDate": "2026-07-22",
  "RequestFor": 0,
  "SessionId": "<SessionId>"
}
```

- `RequestFor`: `0` = download; email presumed `1` **[CONFIRM]**.
- `Margin`: `0` = normal ledger. **MTF hypothesis NOT confirmed** — on the
  test account (X008593) `Margin:0` and `Margin:1` returned **byte-identical
  ledger content** (same extracted text, no "MTF" in filename). Either `Margin`
  isn't the MTF discriminator, or this account simply has no MTF activity to
  differentiate. Still **[CONFIRM]** — needs an account with actual MTF
  holdings.
- `LoginId` = **client code**, NOT the `"JIFFY"` literal the data API uses.
- `Group` = `"GROUP1"` **uppercase** (data API uses `"Group1"`).
- No `FileFormat` field → **PDF only** (no Excel for ledger).

**Response — success (LIVE-CONFIRMED 2026-07-16):**
```json
{ "Status": "Success",
  "Response": "https://client-report.choiceindia.com/PDFReports/<REPORTID>_<ClientId>.pdf",
  "Reason": "" }
```
URL fetched → valid `%PDF`, ~60 KB. **Failure — no data:**
`{ "Status": "Fail", "Response": null, "Reason": "Data not found." }`.

### 4.3 `POST /mis/reports/generate` — CML [FILE] (NEW, third backend)

```http
authType: jwt
source: FINX_ANDROID
authorization: <SSO JWT = frontend accessToken>
from: android_9.2.2.260710
```
```json
{ "reportType": "cml", "searchBy": "client-id", "searchValue": "X04883" }
```

- **JWT auth, not SessionId** (see §1).
- Shape (`reportType`/`searchBy`/`searchValue`) suggests a **generic report
  generator**; only `cml` confirmed.

**Response (LIVE-CAPTURED 2026-07-16, HTTP 200):** envelope is **camelCase**
(differs from Contract Note's PascalCase):

```json
{
  "statusCode": 200,
  "message": "URL generated successfully",
  "devMessage": null,
  "body": {
    "cmlLink": "https://onmedia.choiceindia.com/JF/<hash>/<hash>_CML_<ts>.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=<MASKED>&X-Amz-Date=...&X-Amz-Expires=120&X-Amz-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3DClient_Master_List.pdf&X-Amz-Signature=<MASKED>"
  }
}
```

- Link field: **`body.cmlLink`** (matches spec). It's an **AWS S3 SigV4
  pre-signed URL** (`X-Amz-Expires=120`), fronted by CloudFront.
- Download filename (content-disposition): `Client_Master_List.pdf` (confirms
  the §2.6 CML filename carve-out). PDF verified `%PDF-1.6`, 9002 bytes.
- The stored object timestamp (`_CML_20240201...`) shows the PDF is a **static
  pre-generated S3 object**, not freshly rendered per call.

🔴 **SECURITY — see §7 FLAG B: the "120s single-use" assumption is FALSE in
practice.** Repeat fetches succeed (not single-use), and CloudFront caches by
**path only** (ignores the signed query string), so once any valid link warms
the cache the same S3 path is served for CloudFront's TTL regardless of
signature expiry. Do NOT rely on 120s/single-use as a security boundary; still
fetch server-side and never expose the link.

### 4.4 `POST /middleware-go/report/contract` — Contract Note list [DATA/list]

```http
authorization: <SessionId>
from: Web_finx.choiceindia.com_V_4.6.0.4
```
```json
{ "client_id": "X04883", "from_date": "2024-07-15", "to_date": "2026-07-15" }
```

- snake_case; **no `SessionId` in body** (Go backend).
- No Group/segment variants at request level.

**Response — no data:**
```json
{ "StatusCode": 204, "Message": "No valid contract notes found ...",
  "DevMessage": null, "Body": {} }
```
**Response — success (LIVE-CAPTURED 2026-07-16, HTTP 200):**

```json
{
  "StatusCode": 200,
  "Message": "Success",
  "DevMessage": null,
  "Body": {
    "client_code": "X04883",
    "contractNotes": [
      { "date": "16092024", "file_id": "<~88-char opaque base64 token>",
        "group": "Grp1", "id": "16092024", "invoice_number": "2140106" }
    ]
  }
}
```

⚠️ **Mixed casing**: envelope is PascalCase, the list key `contractNotes` is
camelCase, note fields are snake_case. Per-note fields (exactly 5):

| Field | Type | Notes |
|---|---|---|
| `date` | str | **`DDMMYYYY`** (e.g. `16092024`) — this IS the trade date |
| `file_id` | str | ~88-char opaque base64 token (the download handle) |
| `group` | str | segment — **only `Grp1` seen** (Equity & F&O); ⚠️ casing is inconsistent (`Grp1` ×20, `GRP1` ×1) — **match case-insensitively** |
| `id` | str | **redundant — always == `date`, NOT a unique id.** Key rows by `file_id`, never `id`. |
| `invoice_number` | str | contract-note invoice number |

- 21 notes returned for a 2-year range. **No dual-note (Grp1+MCX same-date)
  case observed** — this account/range has no MCX notes, so the "two file_ids
  on one date" pattern is still unconfirmed (design assumption stands).
- **`Body.client_code`** echoes the requested client; **`Body` is `{}` on the
  204 empty branch** (no `client_code`/`contractNotes`).

**204 empty-branch (captured):**
```json
{ "StatusCode": 204,
  "Message": "No valid contract notes found for the given clientId and date range",
  "DevMessage": null, "Body": {} }
```

🔴 **SECURITY — see §7 FLAG A: this endpoint enforced NO authentication in
testing (returned full data with garbage or absent credentials; authorized
purely on body `client_id`). Treat as a broken-access-control risk.**

#### Per-note download — `POST https://api.choiceindia.com/middleware-go/contract/download` (LIVE-CAPTURED 2026-07-16)

⚠️ **Different host** (`api.choiceindia.com`, not `finx.choiceindia.com`) but
same `/middleware-go` path prefix.

```http
authorization: Session <SessionId>      # note the "Session " prefix (app usage)
content-type: application/json
```
```json
{ "client_code": "X008593", "file_id": "<file_id from the list response>" }
```

**Response**: the **raw PDF bytes directly** (`content-type: application/pdf`,
`%PDF-1.4`), not a URL/envelope. `content-disposition: attachment;
filename=CN_<ClientId>_<group>_<invoice_number>.PDF` (e.g.
`CN_X008593_Grp1_1021635.PDF`). No 120s expiry / signed URL — the bytes come
straight back, so fetch server-side and stream as a file card.

🔴 **SECURITY (extends FLAG A)**: this download endpoint ALSO enforces no auth
— returned the PDF with the bare token, with the `Session ` prefix, AND **with
no `authorization` header at all**. Combined with the unauthenticated list
endpoint, the entire contract-note chain (list `file_id`s → download PDFs) is
reachable with only a `client_code`. The Jini backend must gate `client_code`
by the authenticated widget session; never proxy a user-supplied one.

### 4.5 `POST /api/middleware/GetTaxReportPDF` — Tax/Capital Gain file/email [FILE]

```http
authorization: <SessionId>
from: android_9.2.2.260710
```
```json
{
  "ClientId": "X04883",
  "FinYear": "2024-2025",
  "RequestFor": 2,
  "FileFormat": 2,
  "SessionId": "<SessionId>"
}
```

- `FinYear` `YYYY-YYYY` (not a date range). Supported window is dynamic
  (current + last 2 FYs) — never hardcode the three years.
- `RequestFor`: `2` = download-here · `1` = email (ViewType-compliant).
- `FileFormat`: `1` = PDF · `2` = Excel (confirmed by the 2026-07-16 Excel
  capture).
- No separate Capital Gain API — CG intent routes here (education line only).

**Response — success (LIVE-CONFIRMED 2026-07-16):** `Response` is a **string
file URL** (not an array). The URL shape differs by format:
- PDF: `.../PDFReports/<REPORTID>_<ClientId>.pdf` (fetched → valid `%PDF`)
- Excel: `.../PDFReports/<REPORTID>_<ClientId>_<epoch-ish-number>.xlsx`
  (extra numeric suffix + `.xlsx`; fetched → valid `PK` zip / xlsx)

**Failure:** `{ "Status": "Fail", "Response": null, "Reason": "Data not
available." }` (note: wording is "Data **not available**." here vs "Data not
found." on the other endpoints — don't string-match a single failure Reason).

🔒 Generated URL appears **unauthenticated once created** — treat as sensitive;
backend fetches server-side, never surfaces the raw URL to client or logs.

### 4.6b get-profile — `POST https://mf.choiceindia.com/api/v2/investor/profile/extended` (LIVE-CAPTURED 2026-07-16)

⚠️ **Fourth host** (`mf.choiceindia.com`) + **JWT auth** (the SSO
`accessToken`, same as CML — not the SessionId).

```http
authorization: <SSO JWT = frontend accessToken>
from: Web_finx.choiceindia.com_V_4.6.0.4
content-type: application/json
```
```json
{ "InvCode": "X008593" }
```

**Response**: `{ "Status": "Success", "Response": { …large profile… }, "Reason": "" }`.

🔴 **HEAVY PII — Jini needs exactly ONE field.** The `Response` object contains
extensive sensitive data: `FirstHolderPAN`, full `Address1-3`/`City`/`PinCode`,
`Email`, `MobileNo`, `DateOfBirth`, `Age`, `MaritalStatus`, `RiskLevel`,
`InvestorId`, and a full **`Bank[]`** array (account numbers, IFSC/MICR,
mandate tokens, `bankStatus`).

**DECISION (2026-07-16): extract ONLY `FirstHolderName` → first token → first
name for the Phase-2 greeting; discard everything else.** e.g.
`FirstHolderName: "PRITAM NITIN WAVHAL"` → greet as "Pritam". The full profile
response must **never be logged, stored, traced, or sent to the client** — the
backend reads the first name, keeps it in memory for the session greeting, and
drops the rest. Apply the DeepEval `mask=` PII hook here especially. (This is
also why get-profile is a Phase-2 personalization nicety, not a Phase-1 need —
Phase 1 greets by Client ID.)

### 4.6c Brokerage — `POST https://api.choiceindia.com/middleware-go/v2/get-brokerage-slab` (LIVE-CAPTURED 2026-07-16)

Same host as the contract-note download (`api.choiceindia.com/middleware-go`),
**JWT auth** (SSO `accessToken`).

```http
authorization: <SSO JWT = frontend accessToken>
from: Web_finx.choiceindia.com_V_4.6.0.4
content-type: application/json
```
```json
{ "ClientID": "X008593" }
```

**Response — hybrid envelope** (`StatusCode` **and** `Status`, plus `Response`/
`Reason` — a blend of the two conventions):

```json
{
  "StatusCode": 200,
  "Status": "Success",
  "Response": [
    { "title": "Equity", "list": [
        { "title": "Intraday", "desc": "₹0.10 for trade value of 10 thousand" },
        { "title": "Delivery", "desc": "₹1.00 for trade value of 10 thousand" } ] },
    { "title": "Derivative", "list": [
        { "title": "Stock Future", "desc": "₹20.00 for trade value of 10 thousand" },
        { "title": "Stock Option", "desc": "₹20.00 per order" }, … ] },
    { "title": "Commodity", "list": [ … ] },
    { "title": "Currency",  "list": [ … ] }
  ],
  "Reason": ""
}
```

**`Response` = array of segment groups**, each `{ title: string, list:
[{ title: string, desc: string }] }`. `desc` is **pre-formatted human-readable
rate text** (e.g. "₹0.10 for trade value of 10 thousand", "₹20.00 per order") —
render it verbatim; do NOT parse or compute a rupee figure (matches the
flow-spec rule: rates only, point to the contract note).

🔻 **RENDER DYNAMICALLY (owner note):** brokerage slabs **differ per client** —
the number of segments AND the number of rows per segment are variable. The
card must iterate whatever `Response` returns; **do not hardcode
Equity/Derivative/Commodity/Currency or a fixed row count**. Request key is
`ClientID` (PascalCase, one word). No PDF/email for brokerage (card only).

### 4.6d Holdings — `POST https://finxomne.choiceindia.com/COTI/V1/Holdings` (LIVE-CAPTURED 2026-07-16)

⚠️ **Fifth host** (`finxomne.choiceindia.com`, path `/COTI/V1/…`) and the
**most auth-heavy endpoint — it wants THREE credentials at once:**

```http
authorization: Session <SessionId>          # "Session " prefix
ssotoken: <SSO JWT = frontend accessToken>  # the SSO token, as its own header
from: Web_finx.choiceindia.com_V_4.6.0.4
content-type: application/json
```
```json
{
  "GroupId": "HO",
  "UserCode": "X008593",
  "UserId": "X008593",
  "SessionId": "<SessionId>",
  "Status": "",
  "accessToken": "<FINX-issued JWT (iss:FINX), embeds UserId+SessionId+DeviceId>"
}
```

⚠️ **Credential provenance question**: the body `accessToken` is a **FINX-issued
JWT** (`iss: FINX`), which is a *different* token from the SSO JWT (`iss:
sso.choiceindia.com`) used in the `ssotoken` header and by CML. Where the Jini
backend obtains this FINX JWT in the widget handoff is unresolved — it may be
`CHOICE_FINX_API_KEY` (also `iss:FINX` in `.env`) or minted elsewhere.
**[CONFIRM] before wiring the Holdings flow.**

**Response — success:**
```json
{ "Status": "Success",
  "Response": { "lDictHoldingData": { "<ISIN>": { …holding… }, … }, "BodStatus": 0 },
  "Reason": "" }
```

🔑 **`lDictHoldingData` is an OBJECT keyed by ISIN** (not an array) — iterate
`.values()`. Each holding record:

| Field | Meaning |
|---|---|
| `Sym`, `Name` | trading symbol (`RELIANCE-EQ`) / full name |
| `Seg`, `Token` | segment id, exchange token |
| `Q`, `TotalQtyFromDB`, `SQ` | quantity / DB qty / sellable qty |
| `LTP`, `CP` | last-traded / close price **in paise** (÷100 for ₹: `130330` = ₹1303.30) |
| `ABP`, `ASP` | average buy / sell price **in rupees** (`1297.38`) |
| `PD` | price divisor (100) |
| `MTFQty`, `MTFPrice`, `MTFSellQty` | **MTF position per scrip** (all 0 on this account) |
| `LTT`, `LUT` | last trade / update time (`DD-MM-YYYY HH:MM:SS`) |
| `Basket`, `ML`, `AprQty`, `SaarQ`, `Events`, `TxnId`, `lExchangeScrip` | misc |

⚠️ **Price-unit inconsistency**: `LTP`/`CP` are integer paise; `ABP`/`ASP` are
decimal rupees. Normalize before rendering (÷100 on LTP/CP).

🔻 **This is a live-data (real-time price) endpoint, not a file.** It returns
the current portfolio, not a PDF. If Jini's "Holding Statement" flow should
deliver a **downloadable file** (consistent with the file-delivery standard),
that PDF/download endpoint is **NOT captured [GAP]** — only this live-holdings
data endpoint exists. Decide: render holdings as a data card (like Brokerage),
or capture a separate Holding-statement PDF endpoint.

### 4.6 Documented DATA endpoints (kept for reference / no-data detection)

These return records, not files. Used only if the bot needs to read numbers
in-chat or detect empty ranges; the report flows deliver via the [FILE]
endpoints above.

- **`GetLedgerDetails`** — `{LoginId:"JIFFY", ClientId, Group:"Group1",
  FromDate, ToDate, SessionId}` → **`Response` = array** of ledger records
  (LIVE-CONFIRMED: 133 rows for X008593). First row on a full period = the
  `OPENING` voucher (`Trans_Type:"O"`, `trd_Date:"1900-01-01T00:00:00"`
  sentinel). Record fields (14): `trd_Date` (ISO or null), `vDate`
  (`DD-MM-YYYY` str), `voucher`, `Trans_Type`, `No`, `Code`, `Narration`
  (⚠️ contains third-party PII — DP-transfer narrations include another
  person's name/account), `ChqNo` (num/null), `Debit`, `Credit`,
  `settlement_No`, `Mkt_Type`, `FinStyr` (num), `dt` (ISO). MTF discriminator
  unknown on THIS endpoint.
- **`GetGlobalPNLNew`** — `{UserId=<client code>, ClientId, Group:Cash/Derv/Comm,
  FromDate, ToDate, With_Exp, SessionId}` → **success `Response` = an OBJECT**
  (LIVE-CONFIRMED — all 3 segments returned data for X008593):
  ```json
  { "Status": "Success", "Reason": "",
    "Response": { "Trades": [ /* per-scrip P&L rows */ ], "Expenses": [ /* charges */ ] } }
  ```
  `Trades[]` fields (20, identical across all 3 segments): `Client_Id,
  Scrip_Symbol, Scrip_Name, ISIN, Open_Qty, Open_Rate, Buy_Qty, Buy_Rate,
  Sell_Qty, Sell_Rate, Net_Qty, Net_Amount, Net_Rate, FIFO_Rate, FIFO_Value,
  Booked_PNL, Curr_Price, Current_Value, Notional_FIFO_Open, Net_Notional`.
  Note `ISIN` is **null for F&O and commodity** (real ISIN only for cash
  equity); `Scrip_Symbol` is a numeric code for equity but a contract string
  (e.g. `"IO CE NIFTY 02Jun2026 24100 "`, trailing space) for F&O.
  `Expenses[]` fields: `{Charges: string, Amount: number}` — charge categories
  vary by segment (Cash: CGST/OTHER EXP/SGST/STT; Derv drops STT; Comm adds
  STAMP DUTY/TURN OVER CHARGE; `OTHER EXP` can be negative).

  🔻 **`With_Exp` changes the RESPONSE SHAPE, not just content (LIVE-CONFIRMED —
  big gotcha):**
  - **truthy (`1`/`true`)** → `Response` = **object** `{Trades:[…],
    Expenses:[…]}`
  - **falsy (`0`/`false`)** → `Response` = **bare array** `[…trade records…]`
    (no wrapper, no Expenses)

  The trade-record schema is identical either way — only the envelope differs.
  The server accepts **both int and boolean** (`1`≡`true`, `0`≡`false`; not
  type-strict). **Always send `With_Exp` truthy for a stable object shape**, and
  never blindly access `.Response.Trades` without checking whether `Response`
  is an object or an array.
- **`GetDetailedPNL`** — `{UserId:"neuron", ClientId, Group:"Group1"|"Group23",
  FromDate, ToDate, SessionId}` → **success `Response` = array** (LIVE-CONFIRMED:
  192 rows for Group1/X008593; Group23/commodity returned no data on this
  account). Record fields: `TRADE_DATE, Scrip_Name, SECURITY, Stock,
  COMPANY_CODE, Open_Qty, Open_Rate, Buy_Qty, Buy_Rate, Sell_Qty, Sell_Rate,
  Net_Qty, Net_Rate, Net_Amount`. This is the data side of the Global Detail
  Report; **no file/download endpoint exists for it [GAP]**.

---

## 5. Field-level trap list

1. **`RequestFor` is per-endpoint** (§2): PNL-PDF/Ledger-PDF `0`=download,
   Tax `2`=download; all three `1`=email.
2. **`With_Exp`**: server accepts **both int and boolean** (`1`≡`true`,
   `0`≡`false`, LIVE-CONFIRMED on `GetGlobalPNLNew`) — not type-strict.
   Controls whether charges/`Expenses` are included. Captures show `true` on
   `GetGlobalPNLPDF`, `1` on `GetGlobalPNLNew`; either works.
3. **Ledger `Group` casing**: `"GROUP1"` (PDF endpoint) vs `"Group1"` (data
   endpoint). Send as captured per endpoint until case-insensitivity is
   confirmed **[CONFIRM]**.
4. **Identity field per endpoint** — inconsistent by design:
   - `GetLedgerDetails` → `LoginId = "JIFFY"`
   - `GetLedgerDetailsPDF` → `LoginId = <client code>`
   - `GetGlobalPNLNew` / `GetGlobalPNLPDF` → `UserId = <client code>`
   - `GetDetailedPNL` → `UserId = "neuron"` (literal)
   - Contract Notes → `client_id`
5. **`Margin`** (Ledger PDF): `0` = normal ledger. `1` = MTF is **unconfirmed**
   — `Margin:0` and `Margin:1` gave byte-identical ledgers on the test account
   (no MTF activity). Needs an MTF-holding account to verify; until then send
   `Margin:0` for normal ledger and treat MTF as untested.
6. **Group vocabularies don't mix**: P&L uses `Cash/Derv/Comm`; Ledger &
   Detailed PNL use `Group1/Group23` (`GROUP1` uppercase on the ledger PDF).
7. **Segment mapping (customer-facing → API)**: Equity→Cash, F&O→Derv,
   Commodity→Comm (P&L); Grp1→"Equity & F&O", MCX→"Commodity" (Contract Notes).
8. **Tax/PNL/CML file URLs are sensitive/unauthenticated** — fetch server-side,
   never expose or log. (CML's 120s/single-use is NOT a real boundary — §7
   FLAG B.)
9. **`from:` header** is a build tag, not auth — pick a stable Jini value.
10. **Auth failure is HTTP 401, not 200-with-Fail** — detect by status code,
    and the envelope shape differs per backend (§7 table).
11. **Contract Note fields**: key rows by `file_id` (not `id`, which just
    duplicates `date`); `date` is `DDMMYYYY`; match `group` case-insensitively.

---

## 6. Gap list

**No FILE/download endpoint (data exists, PDF leg not captured):**
- Holding Statement — live data captured (§4.6d), but no PDF/download endpoint
  (decide: data card vs capture a PDF endpoint).
- Global Detail Report — `GetDetailedPNL` data only; no PDF endpoint.

**All flow ENDPOINTS now captured** (2026-07-16): Ledger, MTF Ledger, P&L,
Detailed P&L, Contract Notes (list+download), Tax, Brokerage (§4.6c), CML,
Holding (§4.6d), get-profile (§4.6b), Freshdesk
(`04_freshdesk_api_reference.md`).

**Response schema still unknown:**
- Global Detail Report — `GetDetailedPNL` gives data, but **no file/download
  endpoint exists** for it (the only report with no file path).

**Confirmations still owed:**
- **`Margin:1` on an MTF-holding account** — `Margin:0`/`:1` were byte-identical
  on the test account (no MTF activity), so the MTF discriminator is unverified.
- Email-branch (`RequestFor:1`) responses for `GetLedgerDetailsPDF` — not
  tested (consent: no email branches).
- SessionId acquisition / lifetime / refresh behaviour (the widget receives it
  from the app; lifetime unmeasured).

**Resolved by live captures (2026-07-16):**
- ✅ `GetGlobalPNLPDF` success + no-data failure envelopes.
- ✅ `GetLedgerDetailsPDF` success + failure envelopes; byte-valid PDF.
- ✅ `GetTaxReportPDF` PDF **and** Excel URL shapes + failure ("Data not
  available.").
- ✅ `GetGlobalPNLNew` success schema (`{Trades[], Expenses[]}`, all 3
  segments) + `With_Exp` accepts int & bool.
- ✅ `GetDetailedPNL` success schema (array, 14 fields).
- ✅ `GetLedgerDetails` success schema (133 records).
- ✅ Contract Note list `Body` + **per-note download endpoint** (raw PDF).
- ✅ CML full response + `cmlLink` + expiry behaviour.
- ✅ Auth-failure envelopes per backend.
- ✅ Session↔client binding rule; `from:` header is not source-gating.

---

## 7. Security findings (live testing, 2026-07-16)

> ⚠️ These are **live-production observations on Choice/FinX infrastructure**,
> not chatbot bugs. They are reported so the Jini backend can defend against
> them and so the FinX team can be notified. Not exploited — a single
> non-existent-client probe (`X99999`) confirmed FLAG A; no real client IDs
> were enumerated.

### FLAG A — Contract Note endpoint has NO authentication (IDOR/BOLA)

`POST /middleware-go/report/contract` authorized purely on the body
`client_id`. In testing it returned **HTTP 200 + full data with a garbage
`authorization` header, and with no `authorization` header at all**. A probe
with `client_id: "X99999"` (no auth) returned a valid `204 "No valid contract
notes"` — i.e. the endpoint answers for arbitrary client IDs without any
credential. Any known `client_id`'s contract notes **and their `file_id` PDF
handles** appear retrievable unauthenticated.

**Jini implications:** (1) never trust this endpoint as an auth boundary —
enforce client_id-ownership server-side (the widget's authenticated session
must gate which `client_id` we ever query); (2) treat `file_id` values as
sensitive — never expose to the client or logs; (3) report upstream to the
FinX team.

### FLAG B — CML signed-URL controls nullified by CloudFront caching

The CML `cmlLink` is an S3 SigV4 pre-signed URL with `X-Amz-Expires=120`,
fronted by CloudFront (`onmedia.choiceindia.com`). Testing (four-fetch
timeline):

| Fetch | Timing | Result |
|---|---|---|
| #1 | immediate | 200, valid PDF, `x-cache: MISS` (S3 origin) |
| #2 | back-to-back | 200, valid PDF → **not single-use** |
| #3 | +209s (past 120s) same URL | 200, `x-cache: HIT`, age 150 → **expiry not enforced at edge** |
| #4 | fresh signature, immediate | 200, `x-cache: HIT` of #1's object → **cache key is path-only** |

CloudFront's cache key ignores the signed query string, so once any valid link
warms the cache the same S3 path is served for the CloudFront TTL regardless of
signature validity. **`X-Amz-Expires=120` only bounds a cold cache-miss at the
S3 origin.**

**Jini implications:** do not rely on 120s/single-use as a security boundary
(the §2.6 spec rule is based on a false premise). Still fetch server-side and
never surface the link. The object is a static pre-generated S3 file, so the
CML PDF may be stale relative to the account's current master list.

### Auth-failure envelopes per backend (for error handling / test case H8)

| Backend | Bad credential | HTTP | Body | Header |
|---|---|---|---|---|
| `.NET` `/api/middleware/*` | stale or garbage | **401** | `{"Status":"Fail","Response":"","Reason":"Invalid SessionId"}` | `authstatus: Unauthorized` |
| Go `/middleware-go/report/contract` | garbage or none | **200** | full data (no auth enforced — FLAG A) | — |
| MIS `/mis/reports/generate` | garbage | **401** | `{"statusCode":401,"message":"Invalid Request.","devMessage":null,"body":{}}` | (no `authstatus`) |

Detect auth failure by **HTTP 401, not body shape** (the two 401 envelopes
differ). Stale vs garbage produce an identical `.NET` envelope — no way to
distinguish expired from malformed.
