# loop.md — ticketing-freshdesk

Worktree lead loop state. If it isn't here, it didn't happen.

- Branch: `ticketing-freshdesk` (from main @ cfb22a1 → merge of contracts-foundation PR #1)
- Proposal: `openspec/changes/ticketing-freshdesk/proposal.md` + `manifest.yaml`
- testCommand: `pytest tests/ticketing/`
- doneCondition: manifest.yaml (exact 04 §5 payload; real-time dedupe → note;
  status by id + by ClientID; every non-2xx → ErrorBubble no-leak; call-support chip kept).

## Frozen-surface reconciliation (decided up front, before any code)

Consumed read-only from `app/contracts/` (verified present, PR #1):
- `SessionContext.user_id` (snake_case; `session_id`/`access_token` excluded from serialization).
- `Intent` (16 values, incl. `raise_ticket`/`ticket_status`).
- Wire blocks: `TicketConfirmation`(ticket_id:str, message:str, chips), `ErrorBubble`(code, text, chips),
  `DataCard`(groups), `Chip`/`ChipAction`/`ChipActionKind`.
- `ErrorCode` enum has `E_FETCH` + `E_UNKNOWN` (the two the proposal maps to).
- Frozen tool surface: names `raise_ticket`/`get_ticket_status` (TOOLS), input models
  `RaiseTicketInput`/`TicketStatusInput` (model-facing; identity binds server-side).

Proposal `[CONFIRM]` items resolved against the actually-frozen code:
- **No `ConversationTranscript` frozen type** → define ticketing-owned `TranscriptTurn`
  (role, content); `ConversationTranscript = list[TranscriptTurn]`.
- **No `NoteList` wire type** (only contract-note-specific `NoteListCard`) → status renders
  as `DataCard`. get_ticket_status returns `DataCard | ErrorBubble`.
- **`type` field**: account has REPORTS/CONTRACT NOTES/CHARGES/LOGIN/TRADE AND ORDER/
  GENERAL QUERY/KYC; test ticket left `type` null. Proposal: sending a mapped `type` is
  additive/reversible via config → default ON, config-driven Intent→Type map, cascade stays
  pinned finx-bot/finx-bot-test.
- **Function signatures**: implement the proposal's server-side signatures
  `raise_ticket(session, query_type: Intent, transcript, language, conversation_id)` and
  `get_ticket_status(session, ticket_id)`. ClientID derived from `session.user_id` ONLY —
  no user-supplied client-id parameter exists (structurally enforces the §2.6 session-gate).
- **Error copy**: the frozen `ERROR_COPY` strings are report-generation-specific; ticketing
  emits its own no-leak conversational copy but reuses the frozen `ErrorCode` values
  (E_FETCH retryable / E_UNKNOWN). The "config-driven" mandate (04 §5) covers Freshdesk
  FIELD VALUES, not conversational copy.
- **429**: capture `Retry-After` (log server-side) and return E_FETCH (retryable); do not
  block the async turn. Durable idempotency table deferred (no migration ownership) — in-
  memory session-scoped guard only.

## Tasks completed
- Task 0: tasks.md + loop.md (commit 9a6bf45).
- Task 1: config.py + freshdesk.yaml + __init__ (commit b7f763c).
- Task 2: mapping.py — Intent→Type, subject sub-type, status copy (commit 21c6d1c).
- Task 3: payload.py — TranscriptTurn + build_ticket_payload, HTML escaping (commit d888018).
- Task 4: client.py — async Freshdesk client, Basic auth, 5 endpoints, FreshdeskAPIError (committed).
- Task 5: tool.py — raise_ticket/get_ticket_status, dedupe, idempotency, error→ErrorBubble,
  status DataCards, TICKETING_TOOLS registry (this commit). Smoke-tested: registry keys match
  frozen TOOL_NAMES; payload matches 04 §5; escaping verified; client auth/Retry-After/400 parsing verified.

## Current task
- Task 6: fixture-driven test suite (tests/ticketing/**), then run testCommand.

## Verifier rounds
- (none yet)

## Open questions / escalations
- (none)
