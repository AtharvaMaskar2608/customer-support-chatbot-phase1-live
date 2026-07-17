# loop.md — conversation-orchestrator

Worktree: `/home/choice/projects/customer-support/conversation-orchestrator`
Branch: `conversation-orchestrator` (from main @ cfb22a1)
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
- [ ] T10 — tests/orchestrator/** from the proposal.

Impl notes: `route` binding = `RouterPort.classify(tool_input, context)` (route tool
input_schema IS RouterResult). Fulfilment blocks come from engine.step/rag.answer/
ticketing, never Claude prose. `client_id` on raise_ticket bound from
`context.user_id`, overriding any model-supplied value. Soft close on
`messages_used > message_cap` (10 real turns answered, 11th escalates).

## Verifier rounds

- Round 1: pending (3 fresh spec-verifiers — spec-compliance / edge-cases / contract-surface).

## Open questions / escalations

- None yet. Soft-close→`escalated` mapping (item 3) is a [CONFIRM] resolution, not a
  spec change; flagged here for the verifier panel.
