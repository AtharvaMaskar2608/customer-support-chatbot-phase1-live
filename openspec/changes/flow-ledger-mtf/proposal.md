# Proposal: flow-ledger-mtf

## Why

The Ledger is the second-largest access-friction cluster (62 tickets, "issues with report downloads"; spec §8 Entry-1 chip rationale) and MTF Ledger rides the same spine (owner: "keep MTF in scope", spec §9). Phase 1 fulfils both as one deterministic flow (flow spec "Ledger / MTF Ledger Flow"): report-type → date-range → delivery, then a server-side FinX call and a validated PDF file card. This change is the self-contained Ledger/MTF flow module, registering with the engine's discovery registry and consuming only frozen contracts.

The delivery endpoint is `GetLedgerDetailsPDF` (03 §4.2, live-captured 2026-07-16 — success URL + no-data failure confirmed, byte-valid ~60 KB PDF). The flow spec's older two-step (data API → download API) is **superseded**: this single PDF endpoint generates the file in one call (03 §3, §9 item 7b). **The MTF data path is unproven [CONFIRM]** — on the test account `Margin:0` and `Margin:1` returned byte-identical ledgers (no MTF activity to differentiate; 03 §4.2/§5). We build behind the `Margin` discriminator now, with the caveat that MTF fidelity is unverified until a live MTF-holding capture confirms it.

## What Changes

- New flow module `app/flows/ledger.py` implementing the Ledger/MTF state machine against the frozen `FlowState`/`Step` and `FinXClient` contracts; self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry auto-loads by module presence — **no edit to `app/flows/__init__.py`**.
- Steps: **Report type** (Ledger / MTF Ledger — skipped/pre-completed when intent names it) → **Date range** (presets + calendar) → **Delivery** (PDF here / email — **no Excel**).
- `Margin` discriminator: `0` = normal ledger, `1` = MTF — driven by the report-type step, gated behind the **[CONFIRM]** caveat (MTF byte-identical on the no-MTF test account).
- Per-flow date window: calendar floor **2019-01-01** (older hard-disabled), cap **today+7**, **no max-range clamp** (a 2019→today range is valid; spec §2.5). Preset chips show resolved dates.
- Free-text out-of-window ("ledger for 2017") → conversational nudge with earliest-range chip, no API call.
- Server-side fetch + byte validation; one silent auto-retry on E-FETCH; friendly display filename `Ledger_<range>.pdf` / `MTF_Ledger_<range>.pdf`; no password line.

## Capabilities

### New Capabilities

- `flow-ledger-mtf`: the deterministic Ledger and MTF-Ledger report flow — report-type/date/delivery stepper, `GetLedgerDetailsPDF` server-side call (with the `Margin` MTF discriminator behind a [CONFIRM] caveat), byte-validated PDF file card or masked-email delivery, per-flow 2019 calendar floor and the E-* error taxonomy.

### Modified Capabilities

None — new self-contained flow capability; does not alter frozen contracts.

## Impact

- **New code**: `app/flows/ledger.py` + `tests/flows/test_ledger.py`. No new dependencies.
- **APIs**: consumes `GetLedgerDetailsPDF` server-side only; URL/server filename never surfaced or logged.
- **[CONFIRM] carried forward**: MTF `Margin:1` fidelity (needs an MTF-holding account capture); `RequestFor:1` email branch (untested — no email branches captured); `GROUP1` vs `Group1` case-sensitivity.
- **Lockfiles / migrations / root config**: untouched.

## Files touched

Exactly two files (the complete ownership for this change):

- `app/flows/ledger.py` — the Ledger/MTF flow module. Self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry (`app/flows/__init__.py`, owned by flow-engine-runtime) auto-loads by module presence — no registration import is added anywhere.
- `tests/flows/test_ledger.py` — the fixture-based flow test.

**Not touched**: `app/flows/__init__.py` (discovery registry, owned by flow-engine-runtime), any other `app/flows/*.py`, any shared/contract file, and lockfiles / migrations / root config.

## Contracts & API structure

### FinX endpoint — `POST /api/middleware/GetLedgerDetailsPDF` (03 §4.2)

- **Backend**: Legacy .NET middleware. **Casing**: PascalCase. **Envelope**: `{Status, Response, Reason}`. **Auth**: `authorization: <SessionId>` header **plus `SessionId` in the body**.
- **Consumed via**: the `.NET /api/middleware` adapter (finx-http-adapters, 1) behind `FinXClient`.

Request contract (exactly as captured):

```json
{
  "ClientId": "<client code>",
  "LoginId": "<client code>",
  "Group": "GROUP1",
  "Margin": 0,
  "FromDate": "YYYY-MM-DD",
  "ToDate": "YYYY-MM-DD",
  "RequestFor": 0,
  "SessionId": "<SessionId>"
}
```

- **Identity-field trap**: `LoginId` = **client code**, NOT the `"JIFFY"` literal the data endpoint `GetLedgerDetails` uses. `ClientId` = same client code, bound to the authenticated session.
- **`Group` casing trap**: `"GROUP1"` **uppercase** on this PDF endpoint (the data endpoint uses `"Group1"`). Send as captured; case-insensitivity unconfirmed **[CONFIRM]**.
- **`Margin`**: `0` = normal ledger (confirmed); `1` = MTF **[CONFIRM — unproven]** (`Margin:0`/`:1` byte-identical on the no-MTF test account). Driven by the report-type step.
- **`RequestFor` is per-endpoint**: `0` = download; email presumed `1` **[CONFIRM]** (not tested).
- No `FileFormat` field → **PDF only** (no Excel for ledger).

Response contracts (live-confirmed):

- Success: `{"Status":"Success","Response":"https://client-report.choiceindia.com/PDFReports/<REPORTID>_<ClientId>.pdf","Reason":""}` — URL string; fetched → valid `%PDF`, ~60 KB.
- No-data failure (HTTP 200): `{"Status":"Fail","Response":null,"Reason":"Data not found."}` → `E-NODATA`.
- Auth failure: HTTP **401** `{"Status":"Fail","Response":"","Reason":"Invalid SessionId"}` → session-expiry handling (detect by status code).

Error mapping: no-data → `E-NODATA` (copy: "No ledger entries found between {from} and {to}…"); MTF no-data → plain "No data available for MTF Ledger in that range." (no MTF education); broken bytes → `E-FETCH` (silent retry once); timeout → `E-TIMEOUT`; other → `E-UNKNOWN`. `Reason` logged server-side only.

### Flow step / render-block sequence

1. `[INTENT: ledger | mtf-ledger]` → **Step 1 · Report type** — `chip-row` [Ledger · MTF Ledger] (shown pre-completed + editable when intent named the type).
2. **Step 2 · Date range** — `chip-row` [Last 3 months · Last FY · Custom range] with resolved dates; "Custom" → `calendar` (floor 2019-01-01, cap today+7, no max range). Free-text range → `stepper-card` confirm; out-of-window free-text → `bubble` nudge + earliest-range `chip-row`.
3. **Step 3 · Delivery** — `chip-row` [📄 PDF here · ✉️ Send to email] (no Excel).
4. Generation: `bubble` ack; "Generating your Ledger…" if >5s.
5. Deliver: `file-card` (renamed filename, size, `PDF`, no password, helper line) **or** email-sent `bubble` (masked address); post-delivery `chip-row`.
6. Failures: `error-bubble` + recovery `chip-row`.

Edge cases carried from the flow spec: switching Ledger↔MTF keeps the date range and regenerates (type and range independent); repeat identical request serves cached bytes; "Send it again" bypasses cache; email partial-failure copy for the email leg.

## Dependencies & contracts consumed

- **Imports (frozen, read-only)**: `FlowState`/`Step` + date-window config + FY/date helpers + byte-validation/cache semantics (`flow-engine-contract`); `Intent.LEDGER` / `Intent.MTF_LEDGER` (`router-contract`); `FinXClient` + `GetLedgerDetailsPDF` models + `{Status,Response,Reason}` parser (`finx-client`); `error-taxonomy`; `chat-wire-api` render-block types.
- **Must land first**: contracts-foundation (0). **Consumes at runtime**: `.NET /api/middleware` adapter (1) and the engine executor/cache/discovery registry (2). Builds against contracts + fakes; parallel-safe with 1, 2 once 0 lands.
- **Parallel-safe with the other five flow changes**: no shared file edited; registration via discovery.

## Done condition & test command

Done when: `app/flows/ledger.py` is discovered/registered; a full step walk for both Ledger and MTF Ledger drives the correct `GetLedgerDetailsPDF` request (`LoginId`=client code, `Group:"GROUP1"`, `Margin` per type, `RequestFor` per branch); no-data/auth/fetch failures map to correct E-* bubbles; the 2019 floor / today+7 cap / no-clamp window is enforced; MTF path is exercised behind the [CONFIRM] caveat. Against **fixture-based FinX mocks** — no live API.

Test command: `pytest tests/flows/test_ledger.py`
