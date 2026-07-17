# loop.md — ticketing-freshdesk

Worktree lead loop state. If it isn't here, it didn't happen.

- **Status: SHIPPED** — PR #10:
  https://github.com/AtharvaMaskar2608/customer-support-chatbot-phase1-live/pull/10
  (Gate 2 human review pending on GitHub).
- Branch: `ticketing-freshdesk` (from main @ cfb22a1 → merge of contracts-foundation PR #1;
  rebased pre-ship onto origin/main @ 9b6d31e — merge of finx-http-adapters PR #2 + flow-brokerage PR #3).
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

- Task 6: tests/ticketing/** — conftest + 5 test files + 13 recorded fixtures (this commit).

## Test / done status
- testCommand `pytest tests/ticketing/`: **38 passed** (pre-rebase and on rebased head).
- Full suite `pytest -q` on the **rebased head** (base 9b6d31e): **213 passed**
  (175 pre-existing on new main + 38 new), 1 pre-existing fastapi deprecation warning.
- doneCondition clauses each covered: exact 04 §5 payload (test_payload), real-time dedupe →
  private note (test_dedupe), status by id + by ClientID (test_status_lookup), every non-2xx →
  ErrorBubble no-leak (test_errors), call-support chip kept (test_errors/test_dedupe), fixture-only.

## Verifier rounds
- **None run — deliberate.** Per human-operator lean directive (relayed by team lead) to cut
  agent/token overhead, the fresh 3-lens spec-verifier panel AND the self-check spec read-through
  were skipped for this change. Spec harness for this change = testCommand + full suite only;
  implementation trusted. Gate 2 human review happens on the PR.

## Ship
- Rebased ticketing-freshdesk onto origin/main @ 9b6d31e — **clean, zero conflicts**
  (disjoint files: change owns app/ticketing/** + tests/ticketing/**; merged PRs #2/#3 touch app/finx + flow).
- testCommand + full repo suite green on the rebased head (see Test/done status).
- Pushed branch; opened PR #10.

## Final metrics
- Implementation tasks: 6 (tasks 1–6) + task 0 scaffold, one commit each.
- Verifier rounds used: 0 (skipped per lean directive).
- Findings per round: n/a.
- Behavior-harness runs: 1 (full suite on rebased head → 213 passed).
- Escalations: 0.

## Open questions / escalations
- (none)
