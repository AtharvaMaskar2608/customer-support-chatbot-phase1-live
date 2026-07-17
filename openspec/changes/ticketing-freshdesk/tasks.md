# Tasks: ticketing-freshdesk

Implementation tasks, derived from proposal.md. Each is one commit.

## 1. Scaffold + config-driven Freshdesk defaults
- [ ] Create `app/ticketing/` package (`__init__.py` tool-registration surface).
- [ ] `app/ticketing/freshdesk.yaml` — the 04 §5 config: group_id/source/status/
      priority/tags/subject_template + cascade custom-field names & values
      (cf_product=finx → cf_query_type149508=finx-bot → cf_query_sub_type=finx-bot-test),
      cf_client_id, cf_source="chat box", Intent→Type map, subject sub-type labels.
      Ticketing-owned (NOT app/config/**, which is frozen).
- [ ] `app/ticketing/config.py` — typed loader for freshdesk.yaml + `${ENV}` refs.

## 2. Query-type → Freshdesk field mapping
- [ ] `app/ticketing/mapping.py` — `freshdesk_type_for_intent`, `subject_sub_type_for_intent`,
      status enum → user copy (2 Open / 3 Pending / 4 Resolved / 5 Closed).

## 3. Payload + transcript/metadata assembly
- [ ] `app/ticketing/payload.py` — `TranscriptTurn` type; HTML-escaped transcript
      (`<p>` per turn, escape `< > & "`); metadata block (ClientID, query type,
      language, timestamp, turn count); `build_ticket_payload` producing the exact
      04 §5 field map. ClientID from `session.user_id` only (never user-supplied).

## 4. Async Freshdesk HTTP client
- [ ] `app/ticketing/client.py` — httpx.AsyncClient wrapper; Basic auth
      base64("<KEY>:X"); the 5 endpoints (create, notes, list-by-requester,
      view+stats, search); non-2xx → typed `FreshdeskAPIError`(status/code/field/
      retry_after/reason); honor `Retry-After` on 429; never log ids/URLs in clear.

## 5. Tool functions (raise_ticket / get_ticket_status)
- [ ] `app/ticketing/tool.py` — `raise_ticket`: session-scoped idempotency guard →
      real-time open-ticket check (short-circuit to private note + surface existing) →
      create → `TicketConfirmation` (per-policy TAT, no guaranteed time; call-support
      chip kept). `get_ticket_status`: by id (view+stats) or by ClientID (most-recent-
      first) → `DataCard`. Every non-2xx → `ErrorBubble` (E-FETCH/E-UNKNOWN), no raw leak.

## 6. Tests (fixture-driven, respx; no live calls)
- [ ] `tests/ticketing/` — test_payload, test_mapping, test_dedupe, test_status_lookup,
      test_errors + recorded fixtures (201 create, list, search, view+stats, 400/409/429).

## Done
- [ ] `pytest tests/ticketing/` green; doneCondition satisfied; fresh verifier panel clean.
