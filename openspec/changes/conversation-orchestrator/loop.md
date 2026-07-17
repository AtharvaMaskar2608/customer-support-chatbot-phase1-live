# loop.md — conversation-orchestrator

Status: SHIPPED — PR #4 (Gate 2 pending)

Worktree: `/home/choice/projects/customer-support/conversation-orchestrator`
Branch: `conversation-orchestrator` (rebased onto origin/main @ 9b6d31e — PRs #2
finx-http-adapters + #3 flow-brokerage merged; clean rebase, no conflicts)
testCommand: `pytest tests/orchestrator/`
doneCondition: manifest.yaml (§ Done condition & test command in proposal.md)

## Contract reconciliation ([CONFIRM] markers → frozen `chat-wire-api`)

The proposal inferred wire names before contracts-foundation landed and tagged them
`[CONFIRM]`. Resolved against the frozen contract (never edited):

1. **Single endpoint.** The frozen contract has ONE route, `POST /api/chat`
   (`ChatRequest`→`ChatResponse`). The proposal's separate `POST /api/chat/session`
   does NOT exist. Session bootstrap = the first `/api/chat` turn (`thread_id=None`),
   exactly as the landed stub does. Team lead confirmed: "preserving the session-seed
   contract (greeting + chips + config_slice)".
2. **Types.** Use `Bubble` (not `BotBubble`), `Calendar` (not `CalendarBlock`),
   `ChatRequest`/`ChatResponse` (not `ChatTurn*`/`ChatBootstrapResponse`). Input is
   `message: str | None` OR `action: ChipAction | None` — there is no `TurnInput` union.
   Structured events arrive as `ChipAction` kinds (`select_param`/`open_calendar`/…).
3. **conversation_state.** Frozen enum = greeting/collecting/generating/delivered/
   error/escalated. Proposal's "open"/"soft_closed" → soft close maps to `escalated`.
4. **caps.** Frozen `Caps{messages_used, messages_cap, follow_ups_used}` (not
   follow_up_count on the response — that lives in thread state).
5. **Service entrypoints** (router.classify / engine.step / rag.answer / ticketing.* /
   store.enqueue / configure_tracing) are NOT in the frozen contracts — they are the
   not-yet-landed changes' surfaces. This change owns the PORT protocols (the seam) in
   `app/orchestrator/ports.py` + Phase-1 in-memory adapters; reals swap at Wave 2.
6. **Frozen `select_greeting`** must stay importable from `app.main` (the frozen
   `tests/contracts/test_main_stub.py` imports it) — main re-exports it from bootstrap.

## Tasks

See tasks.md. Status:

- [x] T0 — Read all frozen contracts; baseline `uv run pytest` green (82 passed).
- [x] T1 — ports.py (seams + StepResult/TurnResult + Services bundle).
- [x] T2 — state.py (ThreadState + SessionStateStore).
- [x] T3 — policy.py (caps, sticky-language, escalation blocks).
- [x] T4 — bootstrap.py (session seed; select_greeting moved here, re-exported by main).
- [x] T5 — agentic.py (native tool-use loop; forced route → while stop_reason → ≤3 tool iters).
- [x] T6 — dispatch.py (deterministic structured events, no LLM).
- [x] T7 — orchestrator.py (handle_turn + fan-out enqueue + agent root span).
- [x] T8 — lifecycle.py (startup/shutdown registry) + defaults.py (Phase-1 in-memory adapters).
- [x] T9 — main.py (real FastAPI app + lifespan; frozen test_main_stub still green, 5 passed).
- [x] T10 — tests/orchestrator/** from the proposal (25 tests, all doneCondition items). Also
  landed a disambiguation short-circuit in agentic.py (a disambiguation/follow-up-cap turn ends
  by asking, does not fall through to fulfilment) and fixed the soft-close test setup
  (seed turn_number alongside messages_used — counters advance together).

Impl notes: `route` binding = `RouterPort.classify(tool_input, context)` (route tool
input_schema IS RouterResult). Fulfilment blocks come from engine.step/rag.answer/
ticketing, never Claude prose. `client_id` on raise_ticket bound from
`context.user_id`, overriding any model-supplied value. Soft close on
`messages_used > message_cap` (10 real turns answered, 11th escalates).

## Verifier rounds

- Round 1 (LEAN PASS — per team-lead directive overriding the CLAUDE.md 3-panel default;
  human operator asked to cut verifier-agent overhead and trust implementations more).
  Single self-check by the worktree lead against proposal.md/design.md/tasks.md and
  `git diff main...HEAD`, blocking-issues-only. Findings:
  - One failing test in the working tree (soft-close expected turn_number 11, got 1). Root
    cause: test-setup bug (seeded messages_used but not turn_number), not an implementation
    divergence — the runtime advances both counters together. Fixed the setup.
  - No edits to frozen contract files (`app/contracts/**`, `tests/contracts/**`); diff stays
    within the manifest surface (`app/orchestrator/**`, `app/main.py`, proposal artifacts).
  - Frozen `tests/contracts/test_main_stub.py` still green (5 passed) after main.py rewrite.
  - doneCondition items all covered by tests. No blocking issues remain.

## Metrics

- Verifier rounds used: 1 (lean self-check, no 3-lens panel per directive).
- Findings: round 1 — 1 (test-setup bug, fixed).
- Escalations: 0.
- Rebase: onto origin/main @ 9b6d31e, clean (no conflicts).
- Behavior harness on rebased head: full `uv run pytest` = 200 passed;
  testCommand `pytest tests/orchestrator/` = 25 passed.

## Open questions / escalations

- None. Soft-close→`escalated` mapping (reconciliation item 3) is a [CONFIRM] resolution of a
  pre-contract inference, not a spec change — recorded for the Gate 2 reviewer.
