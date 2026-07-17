# Proposal: ticketing-freshdesk

## Why

When Jini exhausts its follow-up budget (≤2), hits the 10-message cap, cannot ground an answer (B3 numeric-gap, D4 no-match), or the user types "talk to agent" / "raise a ticket", the flow spec (spec §2.4) requires an escalation path: create a Freshdesk ticket carrying the conversation transcript, and answer "ticket status" questions by looking up the customer's open tickets. `docs/technical/04_freshdesk_api_reference.md` captured the live `choicebroking.freshdesk.com` account structure (groups, custom-field cascade, the test ticket #7529083) but no code exists to build a ticket payload, prevent duplicates, or render the confirmation. Without this change, every low-confidence conversation dead-ends instead of handing off, and the workbook blockers D3/D4 (Phase 1) and the K-cluster ticket cases (Phase 2) cannot pass.

This change owns only the server-side ticketing tool and its tests. The render-block types it emits (`ticket-confirmation`, `chip-row`, `error-bubble`, `data-card`, `note-list`) and the `Intent` enum it maps from are frozen contracts consumed from `contracts-foundation`; this change does not define them.

## What Changes

- **Raise-ticket tool** — an async server-side tool the orchestrator invokes on escalation. Builds a `POST /api/v2/tickets` payload from the authenticated session (ClientID = session `userId`, never a user-supplied id — mirrors the spec §2.6 hard rule that Contract-Note-style unauth endpoints must be session-gated), the router's query type, and the conversation transcript (HTML-escaped, one `<p>` per turn, plus a metadata block: ClientID, query type, timestamps, last-N messages, language — workbook K3). Returns a `ticket-confirmation` render block ("Ticket #{id} raised — our team will respond per policy TAT") with the call-support chip kept visible.
- **Config-driven field mapping** — every Freshdesk value (group_id, source, status, priority, tags, subject template, the `cf_product → cf_query_type149508 → cf_query_sub_type` cascade, `cf_source`) is read from a ticketing-owned config, not hardcoded (04 §5 DECISION). Default `group_id 22000168676` (`chatbot-testing`); the FinX routing groups from 04 §0 (`FinX Customer Success` 22000025788, `FinX Technical Support` 22000163931, `FinX Call Support Team` 22000167312, `Finx Franchise Account` 22000167634) are the documented prod switch — a config edit, no code change.
- **Query-type → ticket mapping** — Jini query types map to the Freshdesk `type` (Type) field values that exist in the account (`REPORTS`, `CONTRACT NOTES`, `CHARGES`, `LOGIN`, `TRADE AND ORDER`, `GENERAL QUERY`, `KYC`) and to the `cf_product` cascade. Per 04 §5 the Phase-1 cascade is pinned to `finx-bot`/`finx-bot-test`; the per-report `type`/sub-type mapping is config so it can be turned on once provisioned. [CONFIRM] the test ticket left `type` null — sending a mapped `type` is additive and reversible via config.
- **Duplicate prevention & open-ticket awareness** — before creating, check for an existing open ticket for the ClientID; if found, append a private note and surface the existing ticket status instead of creating a duplicate (workbook K5/K6). Primary check uses the real-time, no-lag list-by-requester endpoint; the search endpoint (minutes of index lag, 04 §4) is secondary only.
- **Ticket-status lookup** — for "where is my ticket" / "ticket status" queries: by explicit id, or by ClientID (most-recent-first), mapping the status enum to user copy (2 Open / 3 Pending / 4 Resolved / 5 Closed). Renders a `data-card`/`note-list`, never raw JSON.
- **Server-side-only I/O + in-band errors** — HTTP Basic auth (`base64("<FRESHDESK_API_KEY>:X")`), all calls server-side, ticket ids/URLs never logged in the clear. Freshdesk errors (400/401/403/404/409/415/429/500) map to conversational `error-bubble`s (E-FETCH / E-UNKNOWN); 429 honors `Retry-After`. No raw error, stack trace, or HTTP code reaches the user (workbook H8 blocker).

## Capabilities

### New Capabilities

- `ticketing-freshdesk`: the server-side Freshdesk integration — raise-ticket tool, duplicate-prevention/open-ticket check, ticket-status lookup, query-type→field mapping, and the confirmation/error render-block assembly. All Freshdesk HTTP lives here behind the frozen render-block and Intent contracts.

### Modified Capabilities

None — consumes frozen `contracts-foundation` capabilities (`chat-wire-api`, `router-contract`, `error-taxonomy`); does not modify them.

## Impact

- **New code**: `app/ticketing/` package + `tests/ticketing/`. No product behavior outside escalation.
- **APIs**: consumes Freshdesk v2 (`choicebroking.freshdesk.com`) server-side only. Adds no new public HTTP route — the orchestrator calls the tool functions directly.
- **Secrets/config**: needs `FRESHDESK_API_KEY` and `FRESHDESK_API_ROOT` in `.env` (not yet in `.env.example` — see conflicts).
- **Out of scope**: multipart transcript-attachment upload (inline HTML transcript only for Phase 1; trim-and-attach is a documented follow-up), customer-visible replies (`/reply`), and a durable idempotency table (see conflicts — deferred to the real-time list check plus a session-scoped guard).

## Files touched

- `app/ticketing/**` (exclusive, per ownership map row 12):
  - `app/ticketing/client.py` — thin async httpx Freshdesk client (auth, `Retry-After`, error→code mapping).
  - `app/ticketing/tool.py` — `raise_ticket` + `get_ticket_status` tool functions.
  - `app/ticketing/payload.py` — payload builder + HTML-escaped transcript/metadata assembly.
  - `app/ticketing/mapping.py` — Intent/query-type → `type` + cascade mapping.
  - `app/ticketing/config.py` (+ bundled `app/ticketing/freshdesk.yaml`) — the config-driven defaults from 04 §5. **Placed under `app/ticketing/`, not `app/config/`** (see conflicts).
  - `app/ticketing/__init__.py` — tool registration surface consumed by the orchestrator.
- `tests/ticketing/**` (exclusive): `test_payload.py`, `test_mapping.py`, `test_dedupe.py`, `test_status_lookup.py`, `test_errors.py`, plus `tests/ticketing/fixtures/` (recorded Freshdesk JSON — no live calls).

Untouched and not owned here: lockfiles, migrations, `app/config/**`, root config, `app/main.py`. `pyproject.toml` is owned by `contracts-foundation` (dependency note below).

## Contracts & API structure

All Freshdesk endpoints per `04_freshdesk_api_reference.md`; base `https://choicebroking.freshdesk.com/api/v2`; auth header `Authorization: Basic base64("<FRESHDESK_API_KEY>:X")`; `Content-Type: application/json`.

### Tool functions (contracts-foundation type names referenced; [CONFIRM] against final class names)

```python
# app/ticketing/tool.py  — consumes contracts-foundation `chat-wire-api` + `router-contract`
async def raise_ticket(
    session: SessionContext,        # frozen: userId(=ClientID), accessToken, platform, page, isDarkTheme
    query_type: Intent,             # frozen router-contract Intent enum → Freshdesk type + cascade
    transcript: ConversationTranscript,  # ordered turns (role, content) for the conversation
    language: str = "en",           # carried as tag lang:<x> + in metadata block
    conversation_id: str | None = None,  # for the session-scoped idempotency guard
) -> TicketConfirmation | ErrorBubble      # frozen render-block wire types

async def get_ticket_status(
    session: SessionContext,
    ticket_id: int | None = None,   # explicit id if the user supplied one; else look up by ClientID
) -> DataCard | NoteList | ErrorBubble
```

- Errors: any Freshdesk non-2xx → `ErrorBubble` with `error-taxonomy` code `E-FETCH` (retryable) or `E-UNKNOWN`; `Reason`/HTTP code logged server-side only. Requester identity always derived from `session.userId`; a user-supplied client id is never forwarded.

### `POST /api/v2/tickets` — create (field map, values from `app/ticketing/freshdesk.yaml`)

| Field | Source | Notes |
|---|---|---|
| `unique_external_id` | `session.userId` (ClientID) | primary requester id — enables real-time list + contact dedupe (04 §5) |
| `name` | client name or ClientID | for auto-created contact |
| `email` | registered client email if resolvable | optional; validate before sending (avoid junk contacts) |
| `subject` | `subject_template.format(query_sub_type, client_id)` | `"[Choice Jini] {query_sub_type} — Client {client_id}"` |
| `description` | HTML-escaped transcript (`<p>` per turn) + metadata block | escape `< > & "`; metadata: ClientID, query type, timestamps, last-N msgs, language |
| `status` | config `2` | Open |
| `priority` | config `2` | Medium |
| `source` | config `7` | Chat |
| `group_id` | config `22000168676` | `chatbot-testing`; prod → a FinX group (config swap) |
| `type` | `mapping.py` from `Intent` | one of REPORTS / CONTRACT NOTES / CHARGES / LOGIN / TRADE AND ORDER / GENERAL QUERY / KYC |
| `tags` | `[choice-jini, chatbot-testing, "lang:"+language]` | config base + language tag |
| `custom_fields.cf_client_id` | `session.userId` | the real ClientID field |
| `custom_fields.cf_product` | config `finx` | cascade level 1 |
| `custom_fields.cf_query_type149508` | config `finx-bot` | cascade level 2 (04 §5 DECISION) |
| `custom_fields.cf_query_sub_type` | config `finx-bot-test` | cascade level 3 (only child of `finx-bot` today) |
| `custom_fields.cf_source` | config `"chat box"` | chatbot-origin source value |

- **Success 201** → read `id`; render `TicketConfirmation(ticket_id=id, tat_copy=<policy TAT, never a guaranteed time — workbook K7>, keep_call_support_chip=True)`.
- **Errors** (04 §3): 400 `{errors:[{field,message,code}]}` (`missing_field`/`invalid_value`/`invalid_field` → E-UNKNOWN, log field), 401/403 → E-UNKNOWN, 409 duplicate → treat as existing-ticket path, 429 → honor `Retry-After` then E-FETCH.

### Duplicate prevention / open-ticket awareness (04 §5, two layers)

1. **Real-time (authoritative, no lag)**: `GET /api/v2/tickets?unique_external_id=<ClientID>&order_by=updated_at&order_type=desc` → filter `status ∈ {2,3}`. If an open ticket on the same query type exists → `POST /api/v2/tickets/{id}/notes` (`body` HTML, `private=true`) and surface that ticket instead of creating.
2. **Secondary/reporting only**: `GET /api/v2/search/tickets?query="cf_client_id:'<ClientID>' AND (status:2 OR status:3)"` — index lags minutes, so never the sole gate.
3. **Session-scoped idempotency guard**: in-memory key `hash(ClientID + query_type + conversation_id)` prevents a double-create within one conversation turn. A durable cross-session idempotency table is **deferred** (see conflicts).

### Ticket-status lookup

- By id: `GET /api/v2/tickets/{id}?include=stats` → status enum → copy.
- By client: the same real-time list endpoint as above (most-recent-first).
- Status map: `2 Open / 3 Pending / 4 Resolved / 5 Closed` → `DataCard`/`NoteList`.

## Dependencies & contracts consumed

- **Consumes frozen `contracts-foundation` (change 0, must land first):** `router-contract` `Intent` enum; `chat-wire-api` render-block types `TicketConfirmation`, `ChipRow` (call-support chip), `ErrorBubble`, `DataCard`, `NoteList`, and `SessionContext`; `error-taxonomy` codes (`E-FETCH`, `E-UNKNOWN`). This change imports these read-only and does not edit them.
- **`pyproject.toml` (owned by change 0):** must declare `httpx` (runtime) and an httpx mock (`pytest-httpx` or `respx`) for tests. Flagged for contracts-foundation, which declares all backend deps up front.
- **Called by `conversation-orchestrator` (change 5):** the orchestrator invokes `raise_ticket`/`get_ticket_status` when the router resolves an escalation/ticket-status intent. This change exposes the tool surface; it does not edit orchestrator files. Can be built now against contracts + fakes; end-to-end only after change 5.
- **Parallel-safe with:** all flow changes (6–11), rag-service (4), tracing (14) — no shared files.

## Conflicts with the ownership map (surfaced per CLAUDE.md)

1. **Freshdesk config placement.** 04 §5 suggests `config/freshdesk.yaml`, but `app/config/**` is owned by `contracts-foundation` and its remote-config schema is **frozen** after it lands. Resolution taken: keep the Freshdesk mapping in a **ticketing-owned** `app/ticketing/freshdesk.yaml` + `app/ticketing/config.py`, so no frozen file is touched. If the owner instead wants Freshdesk defaults in the central remote-config, those keys must be added to `contracts-foundation` *before* it freezes — flagging for that decision.
2. **`.env.example`** has no `FRESHDESK_API_KEY` / `FRESHDESK_API_ROOT` (only `ANTHROPIC/OPENAI/DATABASE/CHOICE/SLACK/...`). Adding them touches a root file not owned here — needs `contracts-foundation`/infra to add the two keys. Surfaced, not edited.
3. **Durable idempotency table.** 04 §5 layer (2) suggests an own-side idempotency store, but migrations are owned solely by `contracts-foundation` (0001) and `conversation-store-writer` (0002+). This change cannot add a migration, so the durable table is **deferred**; Phase-1 dedupe relies on the real-time list endpoint + a session-scoped guard. If a durable store is wanted, `conversation-store-writer` (change 13) should add the column/table.

## Done condition & test command

Done when: `raise_ticket` builds the exact 04 §5 payload from a `SessionContext` + `Intent` + transcript; the real-time open-ticket check short-circuits to a note when an open ticket exists; `get_ticket_status` maps the status enum to user copy by id and by ClientID; every Freshdesk non-2xx maps to an `ErrorBubble` with no raw leak (H8); and the confirmation keeps the call-support chip visible.

Test command: `pytest tests/ticketing/` — green, fully fixture-driven via `pytest-httpx`/`respx` (recorded 201 create, list-by-requester, search, view+stats, and 400/409/429 error bodies). **No live Freshdesk call in CI.**
