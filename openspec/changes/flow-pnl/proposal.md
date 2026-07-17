# Proposal: flow-pnl

## Why

The P&L Statement is the highest-volume report request Jini must serve — 731 tickets, whose top cluster is "difficulty accessing/downloading" (spec §8, Entry-1 chip rationale). Phase 1 fulfils it as a deterministic stepper flow (owner variant **2a**, spec §8/§2.1): the LLM only classifies intent and extracts params; a hardcoded state machine drives segment → date-range → delivery, then calls FinX server-side and delivers a validated PDF as an in-chat file card. This change is the self-contained P&L flow module. It registers with the flow-engine discovery registry and consumes only frozen contracts — no shared files edited.

The delivery endpoint is `GetGlobalPNLPDF` (03_finx_api_reference.md §4.1, live-captured 2026-07-16 — success URL, email-confirmation string, and no-data failure envelope all confirmed). The Detailed-P&L / Global-Detail *data* endpoint (`GetDetailedPNL`) is **out of scope for this change** — it has no captured file/download endpoint **[GAP]** (03 §6), so the "scrip-wise detail" post-delivery hand-off is deferred.

## What Changes

- New flow module `app/flows/pnl.py` implementing the P&L state machine against the frozen `FlowState`/`Step` contract and the `FinXClient` interface; self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry auto-loads by module presence — **no edit to `app/flows/__init__.py`**.
- Three steps: **Segment** (Equity/F&O/Commodity → internal Cash/Derv/Comm) → **Date range** (presets + in-chat calendar) → **Delivery** (PDF here / email).
- Per-flow date-window guardrail: calendar floor **2018-01-01**, cap **today+7**, **2-year max-range clamp** (dynamic, dims start+2yr on first pick) — consumed from the flow's date-window config, not unified with other flows (spec §2.5).
- Free-text param pre-fill: a segment/range parsed from the opening utterance pre-fills a confirm card (2c pattern) and skips the corresponding step.
- Server-side fetch + byte validation (size floor + `%PDF` magic bytes) via the engine; one silent auto-retry on E-FETCH; file card renders with **PDF password = PAN** line and the "Trouble opening it? Tell me." helper.
- Email branch masks the registered email from the polymorphic success `Response` before display.

## Capabilities

### New Capabilities

- `flow-pnl`: the deterministic P&L Statement report flow — segment/date/delivery stepper, `GetGlobalPNLPDF` server-side call, byte-validated PDF file-card (password: PAN) or masked-email delivery, with per-flow calendar guardrails and the E-* error taxonomy.

### Modified Capabilities

None — this is a new, self-contained flow capability; it does not alter the frozen Intent enum, `FinXClient`, or remote-config schema (those are owned by contracts-foundation).

## Impact

- **New code**: `app/flows/pnl.py` + `tests/flows/test_pnl.py`. No new dependencies (all declared in contracts-foundation `pyproject.toml`).
- **APIs**: consumes `GetGlobalPNLPDF` server-side only; the report URL and server filename never reach the client or logs (spec §2.6). Renamed display filename `PnL_<Segment>_<range>.pdf`.
- **Out of scope**: Detailed-P&L / Global-Detail file delivery **[GAP]** (no endpoint captured); Excel format (P&L is PDF-only — no `FileFormat` field on this endpoint).
- **Lockfiles / migrations / root config**: untouched (not assigned to this change).

## Files touched

Exactly two files (the complete ownership for this change):

- `app/flows/pnl.py` — the P&L flow module. Self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry (`app/flows/__init__.py`, owned by flow-engine-runtime) auto-loads by module presence — no registration import is added anywhere.
- `tests/flows/test_pnl.py` — the fixture-based flow test.

**Not touched**: `app/flows/__init__.py` (discovery registry, owned by flow-engine-runtime), any other `app/flows/*.py`, any shared/contract file, and lockfiles / migrations / root config.

## Contracts & API structure

### FinX endpoint — `POST /api/middleware/GetGlobalPNLPDF` (03 §4.1)

- **Backend**: Legacy .NET middleware. **Casing**: PascalCase. **Envelope**: `{Status, Response, Reason}`. **Auth**: `authorization: <SessionId>` header **plus `SessionId` duplicated in the body**.
- **Consumed via**: the `.NET /api/middleware` adapter from `finx-http-adapters` (change 1) behind the frozen `FinXClient` interface — this flow never builds raw HTTP.

Request contract (field names/casing/types exactly as captured):

```json
{
  "ClientId": "<client code>",
  "UserId": "<client code>",
  "Group": "Cash | Derv | Comm",
  "FromDate": "YYYY-MM-DD",
  "ToDate": "YYYY-MM-DD",
  "RequestFor": 0,
  "With_Exp": true,
  "SessionId": "<SessionId>"
}
```

- **Identity-field trap**: `UserId` = `ClientId` = client code (NOT `"JIFFY"`/`"neuron"`). `ClientId` bound to the widget's authenticated session — never user-supplied.
- **`Group` mapping trap**: customer-facing Equity/F&O/Commodity → API `Cash`/`Derv`/`Comm`. Never surface "Derv" to the user. This vocabulary does NOT mix with Ledger's `GROUP1`.
- **`RequestFor` is per-endpoint**: on THIS endpoint `0` = download (URL), `1` = email. (Do not reuse a shared enum — Tax uses `2` for download; 03 §2.)
- **`With_Exp`**: send boolean **`true`** here (the data endpoint `GetGlobalPNLNew` uses int `1`; both accepted, but send the captured type per endpoint). Charges included.
- No `FileFormat` field → **PDF only**.

Response contracts (live-confirmed):

- Download (`RequestFor:0`): `{"Status":"Success","Response":"https://client-report.choiceindia.com/PDFReports/PNLReport_<id>_<ClientId>.pdf","Reason":""}` — `Response` is a URL string.
- Email (`RequestFor:1`): `{"Status":"Success","Response":"PnL Report mail sent successfully to <REGISTERED_EMAIL, UPPERCASED>","Reason":""}` — `Response` is **polymorphic** (URL vs confirmation string) and **leaks the full uppercased registered email → mask before display** (`san***.harsha@gmail.com`).
- No-data failure (HTTP 200): `{"Status":"Fail","Response":null,"Reason":"Data not found."}` → mapped to `E-NODATA`.
- Auth failure: HTTP **401** `{"Status":"Fail","Response":"","Reason":"Invalid SessionId"}` (detect by status code, not body) → session-expiry handling.

Error mapping: `Status:"Fail"`+`Data not found.` → `E-NODATA`; URL 404 / wrong magic bytes → `E-FETCH` (one silent auto-retry, then bubble); timeout → `E-TIMEOUT`; any other non-Success → `E-UNKNOWN`. Copy verbatim from spec §8.4; `Reason` logged server-side, never shown.

### Flow step / render-block sequence

1. `[INTENT: pnl]` → **Step 1 · Segment** — `chip-row` [Equity · F&O · Commodity]; free-text segment pre-fills + confirm.
2. **Step 2 · Date range** — `chip-row` [This FY · This Month · Last 3 months · Custom range]; "Custom" → `calendar` block (floor 2018-01-01, cap today+7, 2-year clamp, out-of-range hard-disabled). Free-text range → `stepper-card` confirm.
3. **Step 3 · Delivery** — `chip-row` [📄 PDF here · ✉️ Email me].
4. Generation: `bubble` ack; "Generating…" indicator if >5s.
5. Deliver: `file-card` (renamed filename, size, `PDF · password: PAN`, helper line) **or** email-sent `bubble` (masked address); post-delivery `chip-row`.
6. Failures: `error-bubble` + recovery `chip-row` per the E-* taxonomy.

## Dependencies & contracts consumed

- **Imports (frozen, read-only)**: `FlowState`/`Step` + per-flow date-window config, FY/date helpers, byte-validation/cache semantics (`flow-engine-contract`); `Intent.PNL` (`router-contract`); `FinXClient` + `GetGlobalPNLPDF` request/response models + `{Status,Response,Reason}` parser (`finx-client`); `error-taxonomy` copy/chips; `chat-wire-api` render-block types.
- **Must land first**: contracts-foundation (0). **Consumes at runtime**: the `.NET /api/middleware` adapter (finx-http-adapters, 1) and the state-machine executor + byte-validation + 15-min cache + discovery registry (flow-engine-runtime, 2). Per the ownership map this flow builds against contracts + fakes and can proceed in parallel with 1 and 2 once 0 has landed.
- **Parallel-safe with the other five flow changes**: no shared file is edited; registration is via engine discovery, not a per-flow edit to `app/flows/__init__.py`.

## Done condition & test command

Done when: `app/flows/pnl.py` is discovered/registered by the engine; a full step walk (segment → range → PDF, and segment → range → email) drives the correct `GetGlobalPNLPDF` request (identity fields, `Group` mapping, `RequestFor` per branch, `With_Exp:true`); no-data/auth/fetch failures map to the correct E-* bubbles; the 2018 floor / today+7 cap / 2-year clamp are enforced; email display is masked. All exercised against **fixture-based FinX mocks** (2026-07-16 captures under `tests/fixtures/finx/`) — no live API.

Test command: `pytest tests/flows/test_pnl.py`
