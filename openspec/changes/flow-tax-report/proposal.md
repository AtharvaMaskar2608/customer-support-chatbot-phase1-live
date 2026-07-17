# Proposal: flow-tax-report

## Why

Tax Report is one of the four fulfilment chips on the Reports-screen entry (spec §8.4) and absorbs every Capital-Gain / Tax-P&L request — there is **no separate Capital-Gain API** (spec §1, flow spec §1.2). Phase 1 fulfils it deterministically (flow spec "Tax Report / Capital Gain Flow"): an optional education line → financial-year selection → format/delivery → server-side call and a validated file card (PDF or Excel) or a both-formats email. This change is the self-contained Tax flow module, registering with the engine's discovery registry.

The endpoint is `GetTaxReportPDF` (03 §4.5, live-captured 2026-07-16 — PDF **and** Excel URL shapes plus the no-data failure confirmed). It breaks the common pattern twice: it takes a `FinYear` (`YYYY-YYYY`) instead of a date range, and its success `Response` is a **string file URL** (treated as sensitive/unauthenticated — server-side fetch, never surfaced or logged). The build-readiness review named the Tax flow a well-specified starting slice (spec §9).

## What Changes

- New flow module `app/flows/tax.py` implementing the Tax state machine against frozen `FlowState`/`Step` and `FinXClient` contracts; self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry auto-loads by module presence — **no edit to `app/flows/__init__.py`**.
- **S0 education line** (conditional — Capital-Gain and Tax-P&L intents only; informational, never blocks) → **S1 Financial year** → **S2 format & delivery** → **S3/S4 generate + deliver**.
- FY model is **dynamic**: `supportedFYs = [currentFY, currentFY-1, currentFY-2]`, `defaultFY = currentFY-1` (pre-highlighted), computed from the frozen FY helpers — **never hardcode the three years** (rolls on 1 April; spec §2.5).
- **AY→FY conversion with explicit confirmation** (EC-2); out-of-window FY → **E-YEAR bubble, no API call** (EC-1).
- Format/delivery: PDF here (`FileFormat:1`) / Excel here (`FileFormat:2`) / Email both (two calls, `RequestFor:1`, FileFormat 1 + 2).
- Server-side fetch of the string URL + byte validation (`%PDF` for PDF, `PK` zip for xlsx); one silent auto-retry on E-FETCH; renamed display filename `Tax_Report_FY<short>.pdf`/`.xlsx`, **no password line**.
- EC-12 partial dual-format email failure copy; masked registered-email display.

## Capabilities

### New Capabilities

- `flow-tax-report`: the deterministic Tax / Capital-Gain report flow — CG/Tax-P&L education lines, dynamic 3-FY selection with AY→FY confirmation and E-YEAR guarding, `GetTaxReportPDF` server-side call in PDF or Excel, byte-validated file card or both-formats masked-email delivery, and the E-* error taxonomy.

### Modified Capabilities

None — new self-contained flow capability; frozen contracts untouched.

## Impact

- **New code**: `app/flows/tax.py` + `tests/flows/test_tax.py`. No new dependencies.
- **APIs**: consumes `GetTaxReportPDF` server-side only; the string URL never reaches the client or logs (sensitive/unauthenticated once created).
- **[OPEN] carried forward**: EC-9 client with no registered email on file (hide email chip / refusal copy if it can occur).
- **Lockfiles / migrations / root config**: untouched.

## Files touched

Exactly two files (the complete ownership for this change):

- `app/flows/tax.py` — the Tax / Capital-Gain flow module. Self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry (`app/flows/__init__.py`, owned by flow-engine-runtime) auto-loads by module presence — no registration import is added anywhere.
- `tests/flows/test_tax.py` — the fixture-based flow test.

**Not touched**: `app/flows/__init__.py` (discovery registry, owned by flow-engine-runtime), any other `app/flows/*.py`, any shared/contract file, and lockfiles / migrations / root config.

## Contracts & API structure

### FinX endpoint — `POST /api/middleware/GetTaxReportPDF` (03 §4.5)

- **Backend**: Legacy .NET middleware. **Casing**: PascalCase. **Envelope**: `{Status, Response, Reason}`. **Auth**: `authorization: <SessionId>` header **plus `SessionId` in the body**. Consumed via the `.NET /api/middleware` adapter (finx-http-adapters, 1) behind `FinXClient`.

Request contract (exactly as captured):

```json
{
  "ClientId": "<client code>",
  "FinYear": "YYYY-YYYY",
  "RequestFor": 2,
  "FileFormat": 1,
  "SessionId": "<SessionId>"
}
```

- **`FinYear`** is `YYYY-YYYY` (long form; chip labels use short `FY 2025-26` — one mapping fn, never format twice). Dynamic window (current + last 2 FYs) — never hardcode.
- **`RequestFor` is per-endpoint and ViewType-compliant here**: `2` = download-here, `1` = email. (Contrast PNL/Ledger, where `0` = download — do NOT share one enum; 03 §2.)
- **`FileFormat`**: `1` = PDF, `2` = Excel (both live-confirmed). No `FileFormat` on the download-here PDF branch defaults to PDF; email branch issues **two** calls (FileFormat 1 then 2).
- **Identity-field trap**: only `ClientId` (no `UserId`/`LoginId` on this endpoint); bound to the authenticated session.

Response contracts (live-confirmed):

- Success: `Response` is a **string file URL** (not an array):
  - PDF → `.../PDFReports/<REPORTID>_<ClientId>.pdf` (fetched → valid `%PDF`).
  - Excel → `.../PDFReports/<REPORTID>_<ClientId>_<epoch-ish>.xlsx` (extra numeric suffix + `.xlsx`; fetched → valid `PK` zip/xlsx).
- Failure: `{"Status":"Fail","Response":null,"Reason":"Data not available."}` — note wording is **"Data not available."** here vs "Data not found." elsewhere; **do not string-match a single Reason** → map any `Status:"Fail"` to `E-NODATA`.
- Auth failure: HTTP **401** `{"Status":"Fail","Response":"","Reason":"Invalid SessionId"}` (detect by status code).

Error mapping: out-of-window FY → `E-YEAR` (no API call); `Status:"Fail"` → `E-NODATA`; URL 404 / wrong magic bytes → `E-FETCH` (silent retry once); timeout → `E-TIMEOUT`; email partial failure → EC-12 copy; other → `E-UNKNOWN`. `Reason` logged server-side only.

### Flow step / render-block sequence

1. `[INTENT: tax | capital-gain | tax-pnl]` → **S0 · education** (`bubble`, CG/Tax-P&L only — informational, non-blocking).
2. **S1 · Financial year** — `chip-row` [FY {default} (pre-highlighted, first) · FY {currentFY} · year-to-date · FY {currentFY-2}] + hint. Free-text FY → `stepper-card` confirm (skip step); AY mention → convert + explicit confirm; out-of-window → `error-bubble` E-YEAR + the 3 FY chips.
3. **S2 · Format & delivery** — `chip-row` [📄 PDF here · 📊 Excel here · ✉️ Email me both].
4. Generation: `bubble` ack; "Generating your Tax Report…" if >5s.
5. Deliver: `file-card` (renamed, size, `PDF`/`Excel`, no password, current-FY provisional caption when FY==currentFY, helper line) **or** email-sent `bubble` (masked address); post-delivery `chip-row` (Also get as {other format} · Email both · Raise a ticket).
6. Failures: `error-bubble` + recovery `chip-row`.

## Dependencies & contracts consumed

- **Imports (frozen, read-only)**: `FlowState`/`Step` + FY helpers (`currentFY`/`supportedFYs`/`defaultFY`, AY→FY mapping) + byte-validation/cache semantics (`flow-engine-contract`); `Intent.TAX_REPORT` (with CG / Tax-P&L routed in — `router-contract`); `FinXClient` + `GetTaxReportPDF` models + `{Status,Response,Reason}` parser (`finx-client`); `error-taxonomy` (incl. E-YEAR + EC-12 copy); `chat-wire-api` render-block types.
- **Must land first**: contracts-foundation (0). **Consumes at runtime**: `.NET /api/middleware` adapter (1) + engine executor/cache/discovery registry (2). Builds against contracts + fakes; parallel-safe with 1, 2 once 0 lands.
- **Parallel-safe with the other five flow changes**: no shared file edited; registration via discovery.

## Done condition & test command

Done when: `app/flows/tax.py` is discovered/registered; a full walk drives `GetTaxReportPDF` with the correct dynamic `FinYear`, `RequestFor` (2 for download / 1 for email), and `FileFormat` (1 PDF / 2 Excel; two calls on email); CG/Tax-P&L intents prepend the education line and still route here; AY→FY converts with confirm; out-of-window FY yields E-YEAR with no API call; the string URL is fetched server-side and byte-validated per format; "Data not available." maps to E-NODATA. Against **fixture-based FinX mocks** (PDF-URL, Excel-URL, and failure fixtures) — no live API.

Test command: `pytest tests/flows/test_tax.py`
