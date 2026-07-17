# Tasks: conversation-orchestrator

Derived from proposal.md + manifest.yaml, reconciled against the **frozen**
`chat-wire-api` contract (contracts-foundation, landed at cfb22a1). Reconciliation
notes for the proposal's `[CONFIRM]` inferences are in loop.md.

- [ ] **T1 — Service seams (ports) + engine result type.**
  `app/orchestrator/ports.py`: `RouterPort` / `EnginePort` / `RagPort` /
  `TicketingPort` / `StorePort` Protocols consuming ONLY frozen data types
  (`RouterResult`, `FlowState`, `RagAnswer`, `RaiseTicketInput/Result`,
  `TicketStatusInput/Result`, `TurnRecord`); `StepResult(blocks, next_state)` and
  the internal `TurnResult`. These are the parallel-dev seams — real modules
  (#2/#3/#4/#12/#13) swap in at Wave 2; in-memory fakes back them until then.

- [ ] **T2 — Thread state + SessionStateStore.**
  `app/orchestrator/state.py`: `ThreadState` (history, turn_number, messages_used,
  sticky language + lock, active `FlowState`, per-ambiguity follow-up counter,
  Anthropic-format message log) and the Phase-1 in-memory `SessionStateStore`
  (`get`/`put`). The live read path — deliberately separate from the store-writer.

- [ ] **T3 — Policy: caps, sticky-language, escalation/soft-close blocks.**
  `app/orchestrator/policy.py`: 10-message soft close, ≤2-follow-up escalation,
  sticky-language lock (English is terminal), and the ticket/call escalation
  ChipRow + close/refusal bubbles. Limits read from `RemoteConfig`, nothing
  hardcoded.

- [ ] **T4 — Bootstrap (session seed).**
  `app/orchestrator/bootstrap.py`: time-aware greeting (IST buckets),
  entry-surface chip selection, `ConfigSlice`, first-turn `ChatResponse`. Owns
  `select_greeting`/`build_config_slice`/`build_session_seed` (moved from the stub);
  `app/main.py` re-exports `select_greeting` so the frozen `test_main_stub` stays green.

- [ ] **T5 — Agentic loop (native tool use).**
  `app/orchestrator/agentic.py`: forced `route` first (`ROUTE_TOOL_CHOICE`), then an
  explicit `while` over `stop_reason` with the frozen tool registry — `tool_use` →
  execute every block server-side via the bindings, append the assistant content +
  ONE user message carrying ALL `tool_result` blocks (`tool_use_id` matched;
  `is_error: true` on failure, never dropped), re-call; `pause_turn` → re-send +
  continue; `end_turn` → break; `refusal` → escalation. ≤3 tool iterations then
  escalate. `client_id` bound from session, never tool args. Fulfilment blocks come
  from the tool result, never Claude prose.

- [ ] **T6 — Deterministic dispatch (structured UI events).**
  `app/orchestrator/dispatch.py`: chip/calendar/stepper actions drive the engine
  directly — NO Claude call. `send_text`/`deep_link` chips carry prefilled text and
  route to the agentic loop instead.

- [ ] **T7 — Orchestrator + fan-out + tracing root span.**
  `app/orchestrator/orchestrator.py`: `Orchestrator.handle_turn` — load state,
  increment turn, cap-check, branch free-text vs structured, assemble the
  `ChatResponse`, wrap in the `agent` root span (thread_id/user_id stitched), and
  non-blocking `store.enqueue(TurnRecord)`. `thread_id` minted once, echoed every turn.

- [ ] **T8 — Lifecycle registry.**
  `app/orchestrator/lifecycle.py`: `on_startup`/`on_shutdown` registry the FastAPI
  lifespan runs; the seam store-writer (#13) and tracing (#14) register into without
  editing `app/main.py`.

- [ ] **T9 — Real `app/main.py`.**
  Replace the stub: FastAPI app + lifespan (runs the registry + Phase-1
  `trace_manager.configure`), `POST /api/chat` wired to a default `Orchestrator`
  (in-memory Phase-1 adapters + real `LLMClient`), session-seed path preserved
  verbatim, `select_greeting` re-exported.

- [ ] **T10 — Tests from the proposal.**
  `tests/orchestrator/**` asserting the done condition: seed greeting/chips;
  free-text→loop / structured→deterministic; faked `tool_use`→`tool_result`→follow-up
  with `tool_use_id` match; parallel `tool_use` (two blocks → one user message);
  `is_error: true` on failed tool; ≤3 iterations→escalation; 10-msg soft close;
  ≤2-follow-up escalation; sticky-language; thread_id once+echoed; enqueue + root span
  invoked without awaiting the DB; client_id from session not body.
