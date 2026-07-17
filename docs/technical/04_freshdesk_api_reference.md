# Freshdesk API Reference — Ticket Integration (Choice Jini)

> Compiled 2026-07-16 from the official docs (developers.freshdesk.com/api, v2;
> anchors cited per section). Covers everything the bot needs: create ticket
> with transcript, duplicate prevention, status lookup, notes/replies.
> **Account: `choicebroking.freshdesk.com`** (API key in `.env` as
> `FRESHDESK_API_KEY`). Live account structure captured in §0 below.

## 0. Live account structure (`choicebroking.freshdesk.com`, verified 2026-07-16)

Real fields/groups the Jini integration should target (from
`GET /ticket_fields` and `GET /groups`):

- **Group `chatbot-testing`** — id **`22000168676`**. This is the closest match
  to the intended "chatbot-test" group; use this `group_id` for Jini tickets in
  testing.
- **FinX routing groups** (if tickets should land with FinX support instead of
  the chatbot test group): `FinX Customer Success` (22000025788),
  `FinX Technical Support` (22000163931), `FinX Call Support Team`
  (22000167312), `Finx Franchise Account` (22000167634). There is **no group
  literally named "finx"** — pick one of these.
- **`cf_client_id`** (label "Client ID", `custom_text`) — ✅ exists; use for the
  ClientID (matches the recommended mapping in §5).
- **`cf_product`** (nested field) includes a **`finx`** choice — this is how
  "finx" is represented as a field value (vs. a group).
- **`ticket_type`** (Type) choices include Jini-relevant values: **`REPORTS`,
  `CONTRACT NOTES`, `CHARGES`, `LOGIN`, `TRADE AND ORDER`, `GENERAL QUERY`,
  `KYC`** (+ many more). Map Jini query types onto these.
- **`cf_source`** includes a **`chat box`** choice — the natural source value
  for a chatbot-originated ticket (alongside the standard `source: 7` Chat).
### The query / sub-query fields — a 3-level cascade on `cf_product`

The "query type" and "sub query type" the team already uses are **NOT** the
`cf_query_type` labeled "Team". They are the **dependent (cascading) levels of
the `cf_product` nested field** (id 22000567031):

| Level | API name | Label | Example |
|---|---|---|---|
| 1 | `cf_product` | Product | `finx` |
| 2 | `cf_query_type149508` | Query Type | `Reports` |
| 3 | `cf_query_sub_type` | Query Sub Type | `Report` |

Each level's valid values depend on the parent. **The existing test ticket
(#7529083, created 2026-07-13, in `chatbot-testing`) used exactly:
`cf_product=finx` → `cf_query_type149508=Reports` → `cf_query_sub_type=Report`**,
plus tag `chatbot-testing`. No `ticket_type` was set (it was `null`).

**Query Types available under `finx`** (level 2) include a purpose-built
**`finx-bot`**, plus: Reports, Funds, Closure, Holdings, Orders, KYC, Login,
Charges, Brokerage, RMS, DP, MTF, Taxation, Technical issue, Service issue,
Modification, and ~45 more.

**Query Sub Types under `finx → Reports`** (level 3) map almost 1:1 onto Jini's
report flows: `CML, Ledger, Contract Note, P&L, Global, Tax Report, Brokerage,
holding, MTF Ledger, DP Statment, ITR reports, Report` (+ others). So a Jini
ticket about, say, a P&L problem sets `cf_query_sub_type = "P&L"`.

⚠️ **Correction to an earlier note in this doc**: these query/sub-query fields
DO exist (they were nested under `cf_product`, so they didn't appear at the top
level of `GET /ticket_fields`). What does **not** exist is a `ticket_type` value
"chatbot-test" (that's the *group* `chatbot-testing`, not a Type).

- Other existing fields (not the query cascade): `cf_query_type` (label
  **"Team"**, ~41 teams), `cf_complaint_type` (QUERY/REQUEST/COMPLAINT/…),
  `cf_classification` (Query/Request/Complaint), `cf_platform` (App/Connect/…).

## 1. Auth (#authentication)

- HTTP Basic Auth: **username = API key, password = any dummy string** (`X`).
  Header: `Authorization: Basic base64("<API_KEY>:X")`.
- Base URL: `https://<domain>.freshdesk.com/api/v2/<resource>`. HTTPS
  mandatory (`ssl_required` otherwise).
- The key belongs to an *agent*; permissions follow that agent's role.

## 2. Create ticket — `POST /api/v2/tickets` (#create_ticket)

`Content-Type: application/json` — **unless attaching files, then everything
goes `multipart/form-data`** (no mixing).

**Requester identity — exactly one required**: `requester_id` | `email` |
`phone` | `twitter_id` | `facebook_id` | `unique_external_id`
(missing all → 400 `missing_field`). New `email`/`phone`/
`unique_external_id` values **auto-create a contact**.

Key fields:

| Field | Type | Notes |
|---|---|---|
| `subject` | string | docs say optional; **treat as required** |
| `description` | string (HTML) | ticket body; **treat as required**; escape user content |
| `status` | enum int | 2 Open (default) · 3 Pending · 4 Resolved · 5 Closed |
| `priority` | enum int | 1 Low (default) · 2 Medium · 3 High · 4 Urgent |
| `source` | enum int | 1 Email · 2 Portal (default) · 3 Phone · **7 Chat** · 9 Feedback Widget · 10 Outbound Email |
| `type` | string | must match a configured Type value |
| `tags` | string[] | freeform |
| `cc_emails` | string[] | |
| `custom_fields` | object | `{"cf_name": value}` — keys must exist in the portal first |
| `attachments` | file[] | multipart only, **total ≤ 20 MB** |
| `name` | string | requester name for auto-created contacts |
| `responder_id` / `group_id` / `email_config_id` / `product_id` | number | portal-dependent IDs |

**Success: HTTP 201** + `Location` header + full ticket object; **`id`** is
the ticket number the bot shows ("Ticket #{id} raised… within 24 hours").
Response also includes `description_text` (plain), `created_at`,
`custom_fields{}`, `tags[]`, etc.

## 3. Errors & rate limits (#errors, #rate_limit)

Validation error body:
`{"description":"Validation failed","errors":[{"field","message","code"}]}`.
Codes to handle: `missing_field`, `invalid_value`, `duplicate_value`,
`datatype_mismatch`, `invalid_field`, `invalid_json`, `inaccessible_field`,
`readonly_field`, `require_feature`, `inconsistent_state`, `access_denied`,
`invalid_credentials`, `ssl_required`.

HTTP: 400 validation · 401 bad key · 403 permission · 404 bad id/domain ·
409 conflict/duplicate · 415 bad content-type · **429 rate limited** ·
500 server.

Rate limits: account-wide hourly quota by plan (3000–5000). Every response
carries `X-RateLimit-Total` / `-Remaining` / `-Used-CurrentRequest`; on 429
honor **`Retry-After`** (seconds). `include=` embeds and search cost extra
credits (2 per embed).

## 4. Supporting endpoints

- **View ticket**: `GET /api/v2/tickets/{id}` (+`?include=stats` →
  `resolved_at`, `closed_at`, `first_responded_at`; `?include=conversations`
  → up to 10, costs 2 credits). The "ticket status" lookup by id.
- **Search**: `GET /api/v2/search/tickets?query="<encoded>"` — query in
  double quotes, ≤512 chars, `:` `:>` `:<` `AND` `OR` `()`; queryable:
  status/priority/type/tag/agent_id/group_id/date fields/**`cf_` custom
  fields**. Max 30/page, 10 pages. ⚠️ **Index lags minutes** — not
  sufficient alone for dedupe.
- **List by requester (real-time, no lag)**: `GET /api/v2/tickets?email=` |
  `?requester_id=` | `?unique_external_id=` (+`updated_since`, `order_by`,
  `per_page` ≤100).
- **Add note**: `POST /api/v2/tickets/{id}/notes` — `body` (HTML, required),
  `private` (default true), `attachments[]`. For appending context to an
  existing ticket.
- **Add reply** (customer-visible): `POST /api/v2/tickets/{id}/reply`.
- **Discover custom fields**: `GET /api/v2/ticket_fields` — returns each
  field's `name` (`cf_*`), `type`, `choices[]`. **Run once after
  provisioning.**

## 5. Recommended Jini mapping

```json
POST /api/v2/tickets
{
  "email": "<registered_client_email>",
  "unique_external_id": "<ClientID>",
  "name": "<client_name_or_ClientID>",
  "subject": "[Choice Jini] <query_sub_type> — Client <ClientID>",
  "description": "<html-escaped transcript + metadata block>",
  "status": 2,
  "priority": 2,
  "source": 7,
  "group_id": 22000168676,
  "tags": ["choice-jini", "chatbot-testing", "lang:<language>"],
  "custom_fields": {
    "cf_client_id": "<ClientID>",
    "cf_product": "finx",
    "cf_query_type149508": "finx-bot",
    "cf_query_sub_type": "finx-bot-test"
  }
}
```

**DECISION (2026-07-16): use the `finx-bot` bucket as-is.** All Jini tickets set
the query cascade to `cf_product=finx` → `cf_query_type149508=finx-bot` →
`cf_query_sub_type=finx-bot-test` (the only child value currently provisioned
under `finx-bot`). No per-report granularity for now; if that's wanted later,
add sub-type choices under `finx-bot` in the Freshdesk admin portal.

**DECISION (2026-07-16): every value above is CONFIG-DRIVEN, not hardcoded.**
None of the group id, product, query type, sub-type, source, priority, status,
tags, or subject template may be baked into code — they live in the config
folder so they can change without a redeploy (consistent with the project's
externalized-config principle, spec §2.2). Suggested `config/freshdesk.yaml`:

```yaml
freshdesk:
  api_root: ${FRESHDESK_API_ROOT}      # secrets stay in .env, not config
  api_key_env: FRESHDESK_API_KEY
  defaults:
    group_id: 22000168676              # chatbot-testing
    source: 7                          # Chat
    status: 2                          # Open
    priority: 2                        # Medium
    tags: [choice-jini, chatbot-testing]
    subject_template: "[Choice Jini] {query_sub_type} — Client {client_id}"
  custom_fields:
    product: finx                      # cf_product
    query_type: finx-bot               # cf_query_type149508
    query_sub_type: finx-bot-test      # cf_query_sub_type
    client_id_field: cf_client_id
  # optional future: per-report query_sub_type overrides once provisioned
  # query_sub_type_by_flow: { ledger: Ledger, pnl: "P&L", ... }
```

The ticket-builder reads these keys; swapping to a FinX group, or to
`Reports`+per-report sub-types later, is a config edit only.

Other notes:
- Send all three cascade levels; the sub-type must be a valid child of the
  query type, so `finx-bot` pairs only with `finx-bot-test` today (see §0).
- `group_id: 22000168676` = the `chatbot-testing` group (swap for a FinX group
  in production if desired).
- `cf_client_id` is the real ClientID field. Language has no native field yet —
  carry it as a tag (`lang:<x>`) or in the description until a field is made.

- Transcript → `description` (HTML-escaped, turns wrapped in `<p>`); if huge,
  trim in description + attach full log as `.txt` (multipart).
- ClientID → `cf_client_id` custom field (queryable/reportable) **and**
  `unique_external_id` (enables the real-time list endpoint + contact
  dedupe); tag as cheap secondary.
- **Duplicate prevention (two layers)**: (1) pre-create check
  `search/tickets?query="cf_client_id:'<ClientID>' AND (status:2 OR status:3)"`
  → if found, `POST /tickets/{id}/notes` instead of creating; (2) own-side
  idempotency store (hash of ClientID+query_type+conversation_id →
  ticket_id) because search indexing lags; real-time fallback:
  `GET /tickets?unique_external_id=<ClientID>`.
- **Status lookup**: by id `GET /tickets/{id}?include=stats`; by client
  `GET /tickets?unique_external_id=<ClientID>&order_by=updated_at&order_type=desc`.
  Map status enum → user copy (2 Open / 3 Pending / 4 Resolved / 5 Closed).

## 6. Gotchas

- `description`/note `body` are **HTML** — escape `< > & "` in user text.
- Attachments force full multipart (`-F` for every field); ≤20 MB total.
- Auto-created contacts from typo'd emails = junk contacts — validate first.
- `cf_*` keys, `type` values, `group_id`/`email_config_id` must be
  provisioned in the portal before use (else 400 `invalid_field` /
  `invalid_value`).
- Search: minutes of index lag, 300-result cap — combine with the real-time
  list endpoint.
- Budget rate credits; honor `Retry-After`, watch `X-RateLimit-Remaining`.
