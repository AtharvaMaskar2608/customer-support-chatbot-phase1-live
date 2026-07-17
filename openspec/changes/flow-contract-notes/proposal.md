# Proposal: flow-contract-notes

## Why

Contract Notes are a recurring access-friction cluster (9 CN tickets in the access category; spec §8) and the flow introduces the note-list card primitive (spec §8.2) that no other flow needs. Phase 1 fulfils it deterministically (flow spec "Contract Note Flow"): one date step → a per-trading-day note list → per-note server-side download → in-chat file card, with bulk = email-all only. This change is the self-contained Contract Note flow module.

Both endpoints are captured (03 §4.4, live 2026-07-16): the **list** endpoint `POST /middleware-go/report/contract` (Body is `file_id`-keyed) and the **per-note download** `POST api.choiceindia.com/middleware-go/contract/download` (returns raw PDF bytes directly). **SECURITY (03 §7 FLAG A):** both endpoints enforced **no authentication** in testing (returned full data / PDF bytes with garbage, `Session `-prefixed, or absent credentials; authorized purely on the body `client_id`/`client_code`). The Jini backend **MUST bind `client_id`/`client_code` to the authenticated widget session and never proxy a user-supplied one**, and must treat `file_id` values as sensitive (never to client or logs).

## What Changes

- New flow module `app/flows/contract_notes.py` implementing the CN state machine against frozen `FlowState`/`Step` and `FinXClient` contracts; self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry auto-loads by module presence — **no edit to `app/flows/__init__.py`**.
- Step 1 **Date range** (presets + calendar) → Step 2 **fetch & branch** on the list envelope `StatusCode` → Step 3 **per-note download** → Step 4 **email branch** (single or bulk).
- Note-list card: **10 rows/page** (remote-config `page_size`), month dividers, rows keyed by **`file_id`**, segment badge (Grp1 → "Equity & F&O", MCX → "Commodity") **only on dual-note days**; footer chips ✉️ Email all N · 📅 Change dates.
- Narrow-nudge at **50 notes** (remote-config threshold) before rendering the list.
- Per-flow date window: floor **2018-01-01**, cap **today** (no +7 — notes exist only for completed trading days), **no max range**.
- No PDF password (CN PDFs unprotected). Download failure → **one silent retry**, then the incomplete-file bubble. Two-API mechanics never surfaced to the user.
- `client_id`/`client_code` sourced from the authenticated session only (FLAG A defense); `file_id` never leaves the backend.

## Capabilities

### New Capabilities

- `flow-contract-notes`: the deterministic Contract Note flow — date-range step, `file_id`-keyed paginated note-list card, per-note raw-PDF server-side download and byte-validated file card, email-all bulk branch, per-flow 2018-floor/today-cap calendar, session-bound `client_id` enforcement (FLAG A defense), and the E-* error taxonomy.

### Modified Capabilities

None — new self-contained flow capability; frozen contracts untouched.

## Impact

- **New code**: `app/flows/contract_notes.py` + `tests/flows/test_contract_notes.py`. No new dependencies.
- **APIs**: consumes the CN list + per-note download endpoints server-side only. Renamed display filename `Contract_Note_<date>.pdf` (+`_MCX` on the commodity note).
- **Security**: this change is the primary place FLAG A is defended — `client_id`/`client_code` bound to session, never pass-through; report to the FinX team is out of scope here (backend concern).
- **[CONFIRM] carried forward**: the dual-note (Grp1+MCX same-date) case is **unobserved** — the "two `file_id`s on one date" segment-badge path is a design assumption (03 §4.4); EC-3 "today's note" publish time is **[OPEN]**.
- **Lockfiles / migrations / root config**: untouched.

## Files touched

Exactly two files (the complete ownership for this change):

- `app/flows/contract_notes.py` — the Contract Note flow module. Self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry (`app/flows/__init__.py`, owned by flow-engine-runtime) auto-loads by module presence — no registration import is added anywhere.
- `tests/flows/test_contract_notes.py` — the fixture-based flow test.

**Not touched**: `app/flows/__init__.py` (discovery registry, owned by flow-engine-runtime), any other `app/flows/*.py`, any shared/contract file, and lockfiles / migrations / root config.

## Contracts & API structure

### FinX endpoint 1 — list: `POST /middleware-go/report/contract` (03 §4.4)

- **Backend**: Go middleware (`finx.choiceindia.com`). **Casing**: snake_case request. **Envelope**: `{StatusCode, Message, DevMessage, Body}` (PascalCase envelope keys; note mixed casing inside `Body`). **Auth**: `authorization: <SessionId>` header only — **no `SessionId` in body**.

```json
{ "client_id": "<client code>", "from_date": "YYYY-MM-DD", "to_date": "YYYY-MM-DD" }
```

Response — success (live-captured):

```json
{ "StatusCode": 200, "Message": "Success", "DevMessage": null,
  "Body": { "client_code": "<client code>",
    "contractNotes": [
      { "date": "DDMMYYYY", "file_id": "<~88-char opaque base64 token>",
        "group": "Grp1", "id": "DDMMYYYY", "invoice_number": "<str>" } ] } }
```

- **Mixed casing trap**: envelope PascalCase, list key `contractNotes` camelCase, per-note fields snake_case.
- **Field traps**: `date` is **`DDMMYYYY`** (this IS the trade date); **key rows by `file_id`, never `id`** (`id` always == `date`, not unique); match `group` **case-insensitively** (`Grp1`/`GRP1` both seen). Only `Grp1` observed → "Equity & F&O"; `MCX` → "Commodity"; no other groups.
- No-data: `{"StatusCode":204,"Message":"No valid contract notes...","DevMessage":null,"Body":{}}` (empty `Body`) → `E-NODATA` with the mandatory "notes are only generated for days you traded" explainer.

Branch on **body `StatusCode`, never HTTP status**: 204 → no-data bubble; exactly 1 note → skip list, deliver directly; 2+ → note-list card.

### FinX endpoint 2 — per-note download: `POST https://api.choiceindia.com/middleware-go/contract/download` (03 §4.4)

- **Different host** (`api.choiceindia.com`, same `/middleware-go` prefix). **Auth**: `authorization: Session <SessionId>` (note the `Session ` prefix). **Consumed via** the `api.` Go adapter (finx-http-adapters, 1).

```json
{ "client_code": "<client code>", "file_id": "<file_id from the list response>" }
```

- **Response is the raw PDF bytes directly** (`content-type: application/pdf`, `%PDF-1.4`) — NOT a URL or envelope. `content-disposition: filename=CN_<ClientId>_<group>_<invoice_number>.PDF`. Backend streams bytes as a file card after size + magic-byte validation.
- 🔴 **FLAG A extends here** — download also returned bytes with no/garbage auth; enforce `client_code` = session-bound; never expose `file_id`.

Error mapping: 204 → `E-NODATA`; download 404 / 0 bytes / wrong magic bytes → one silent retry then `E-FETCH`; timeout → `E-TIMEOUT`; other → `E-UNKNOWN`. Two-API mechanics never surfaced.

### Flow step / render-block sequence

1. `[INTENT: contract-notes]` → **Step 1 · Date range** — `chip-row` [Last trading day · Last 7 days · This month · Custom range] with resolved dates; "Custom" → `calendar` (floor 2018-01-01, cap today, no max range). Free-text single-day → skip chips.
2. **Step 2 · Fetch & branch** — list call → branch on `Body.StatusCode`. `>50` notes → narrow-nudge `bubble` + `chip-row` [✉️ Email all N · 📅 Narrow the range] before rendering.
3. Render: `note-list` card (10/page, Show more, month dividers, dual-note segment badges, keyed by `file_id`) with footer `chip-row`.
4. **Step 3 · Per-note delivery** (row tap / single-note) — download call → `file-card` (renamed, size, `PDF`, no password, helper line); post-delivery `chip-row` [✉️ Email this note · 📅 Other dates].
5. **Step 4 · Email branch** — single or bulk email-all `bubble` (masked address) + fallback `chip-row`.
6. Failures: `error-bubble` + recovery `chip-row`.

## Dependencies & contracts consumed

- **Imports (frozen, read-only)**: `FlowState`/`Step` + date-window config + byte-validation/cache semantics (`flow-engine-contract`); `Intent.CONTRACT_NOTES` (`router-contract`); `FinXClient` + CN list/download models + the Go `{StatusCode,Message,DevMessage,Body}` parser (`finx-client`); remote-config `page_size`/`note_threshold` keys (`remote-config`); `error-taxonomy`; `chat-wire-api` render-block types incl. the note-list card.
- **Must land first**: contracts-foundation (0). **Consumes at runtime**: the Go `finx.` and `api.` adapters (1) and the engine executor/cache/discovery registry + note-list assembly (2). Builds against contracts + fakes; parallel-safe with 1, 2 once 0 lands.
- **Parallel-safe with the other five flow changes**: no shared file edited; registration via discovery. **Coordination note**: relies on the widget shell (change 15) implementing the `note-list` render-block per the frozen `chat-wire-api` wire type.

## Done condition & test command

Done when: `app/flows/contract_notes.py` is discovered/registered; a full walk drives the list call (session-bound `client_id`, snake_case, header-only auth), branches correctly on `StatusCode` (204 / 1-note / 2+-note / >50-nudge), renders the note-list keyed by `file_id` with correct segment badges, and downloads a note via the `api.` host with the `Session ` prefix, validating raw PDF bytes; download failure triggers one silent retry then `E-FETCH`; no `client_id`/`file_id` is ever taken from user input or logged. Against **fixture-based FinX mocks** (CN list Body + raw-PDF download fixtures) — no live API.

Test command: `pytest tests/flows/test_contract_notes.py`
