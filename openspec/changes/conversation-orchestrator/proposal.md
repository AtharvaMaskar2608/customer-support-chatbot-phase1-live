# Proposal: conversation-orchestrator

## Why

Contracts-foundation ships a `POST /api/chat` **stub** and all the wire/router/engine
contracts, but nothing yet runs a conversation. Per `02_technical_spec.md` §2.3 the
lifecycle — URL-param session bootstrap → time-aware greeting + entry chips → first
message → router → flow-engine/RAG/ticket → assembled render blocks → async persist +
trace — has no owner. This change is that owner: the single request/response brain that
turns one user turn into one ordered array of render blocks, enforces the §2.4 caps and
§8.5 sticky-language rule, and fans out to the store-writer and tracing hooks. It is the
**sole owner of `app/main.py` after contracts-foundation lands** (map row 5), replacing the
stub so the FastAPI app is wired exactly once.

It is built to proceed in parallel: it consumes the frozen router/flow-engine interfaces
and calls RAG/ticketing/store/tracing through their published entrypoints, backed by
**in-memory fakes** in unit tests. Integration tests swap the real modules in as changes
2/3/4/12/13/14 land.

## What Changes

- **Session bootstrap** — validate the URL-param `SessionContext` (`userId`, `sessionId`,
  `accessToken` JWT, `isDarkTheme`, `platform`, `page`) server-side; derive the display
  Client ID **from the authenticated session, never from user-supplied input** (§2.6 / `03`
  §7 FLAG A defense); generate a `thread_id` (`uuid4`) once per session and return it.
- **Greeting + entry chips** — pick a time-aware greeting from remote-config `greeting pool`
  (server-clock IST buckets: morning 06:00–09:00, market 09:15–15:30, post-market
  15:30–23:00, else default; §8.4 copy), select the entry surface from `page` (entry-1
  Support "Popular right now" vs entry-2 Reports "Which report do you need…"), and emit the
  matching remote-config chip set. Nothing hardcoded — greeting/chips/limits all read from
  `remote-config`.
- **Per-turn pipeline (native tool-use agentic loop, Anthropic customer-support pattern)** —
  one turn = load thread state → increment turn number → cap check → dispatch. There are two
  dispatch modes:
  - **Free-text turns** run the agentic loop, **not** prompt-then-parse-JSON. The Claude call
    (via `llm-client`) carries the **frozen tool registry** (contracts-foundation
    `app/contracts/tools.py`: `route` / `get_*_report` / `search_kb` / `raise_ticket` /
    `get_ticket_status`). The loop is an explicit `while` over `stop_reason`:
    **`tool_use`** → execute **all** `tool_use` blocks from the assistant message
    **server-side** via the registry bindings (report tools → flow-engine entry, `search_kb` →
    rag-service, `raise_ticket`/`get_ticket_status` → ticketing), append the assistant content
    blocks plus a **single** user turn carrying **all** `tool_result` blocks (each matching its
    `tool_use_id`; splitting them across messages silently degrades parallel tool use), and
    re-call; **`pause_turn`** → re-send the response and continue; **`end_turn`** → break;
    **`refusal`** → map to the escalation chips. A tool execution that fails returns its
    `tool_result` with **`is_error: true`** — never dropped. Tool inputs arrive
    API-validated (`strict: true` on the frozen definitions), so the orchestrator does **not**
    re-validate tool args — it validates only session-derived fields (the `client_id` binding).
    The final assistant text plus the engine-assembled render blocks form the response.
    **Bounded: ≤3 tool iterations per turn**, then escalate to the ticket/call chips.
  - **Structured UI events** (chip tap / calendar pick / stepper edit) **bypass the LLM
    entirely** and drive the flow-engine deterministically — no Claude call on those turns.

  Fulfilment stays deterministic **inside** the tools: the flow-engine validates date
  windows/FY/bytes and assembles file cards (§2.2 preserved) — Claude never fabricates report
  content. Non-streaming, one JSON per turn (contracts decision); the widget shows
  "Generating…" past 5s — the server just responds when ready.
- **Caps & escalation** — enforce the remote-config **10-message cap** (soft close: past the
  cap the orchestrator short-circuits to a close bubble + `🎫 Raise a ticket` / `📞 Call
  support` chips) and the **≤2 follow-up cap per ambiguity** (a third unresolved
  disambiguation escalates to the same ticket/call chips instead of asking again).
- **Sticky-language rule** — detect language on the first user text; once a turn resolves to
  English, the thread stays English thereafter (§8.5); persisted in thread state.
- **Thread state** — Phase-1 in-process `SessionStateStore` keyed by `thread_id` holding
  history, turn number, sticky language, active `FlowState`, and the per-ambiguity follow-up
  counter. This is the **live read path** and is deliberately separate from the store-writer
  table (which is async, write-only, analytics/fine-tuning — a lost row never affects the
  live conversation). Marked as the single-process Phase-1 choice; Redis/DB-backed is a later
  swap behind the same interface.
- **Fan-out** — after the response is assembled, hand the completed turn to the store-writer
  via its non-blocking `enqueue()` (bot latency never waits on the DB), and wrap the whole
  turn in the tracing root `agent` span with `thread_id`/`user_id` stitched on. Startup wires
  `configure_tracing(...)` and the store-writer lifecycle in the FastAPI lifespan.

## Capabilities

### New Capabilities

- `conversation-orchestrator`: the runtime that bootstraps a session, runs the per-turn
  router→dispatch→assemble pipeline, enforces the message/follow-up caps and sticky-language
  rule, owns live thread state, and fans out to persistence + tracing — exposed as
  `POST /api/chat/session` (bootstrap) and `POST /api/chat` (turn) on the FastAPI app.

### Modified Capabilities

- `chat-wire-api` (contracts-foundation): **consumed, not modified** — the orchestrator
  *implements* the `POST /api/chat` route that contracts-foundation defined as a stub. It
  imports every wire type and does not redefine any.

## Impact

- **New code**: `app/orchestrator/**` (bootstrap, turn pipeline, dispatch, session-state
  store, cap/language/escalation policy, fan-out wiring) and the real `app/main.py` (FastAPI
  app + lifespan) replacing the contracts-foundation stub.
- **APIs**: implements `POST /api/chat/session` and `POST /api/chat`; all FinX/Freshdesk work
  stays inside the dispatched services (server-side only) — the orchestrator itself makes no
  outbound FinX/Freshdesk calls, it only gates `client_id` by session.
- **Downstream/dependencies**: depends on contracts-foundation (#0) landing first; runs in
  parallel with flow-engine (#2), llm-router (#3), rag (#4), ticketing (#12), store-writer
  (#13), tracing (#14) via interfaces + fakes.
- **Out of scope**: no flow logic, no router prompts, no RAG retrieval, no ticket API, no DB
  writer internals, no tracing implementation — those live in their own changes. No render-block
  *components* (that's widget-shell #15); the orchestrator only emits the wire types.

## Files touched

Exclusive to this change (map row 5) — nothing outside it:

- `app/orchestrator/**` — new package (bootstrap, turn pipeline, dispatch, session state,
  policy, fan-out).
- `app/main.py` — **replaces the contracts-foundation stub; sole owner post-contracts.**
- `tests/orchestrator/**` — unit tests with in-memory fakes of router/engine/rag/ticketing/
  store/tracing.

Untouched (not assigned here): lockfiles / `pyproject.toml`, any migration, root config, and
every shared read-only contract file (`app/contracts/*`, `app/config/*`, `app/llm/client.py`,
`app/finx/*`). Startup *calls* the store-writer and tracing hooks but **does not edit** their
files (`app/store/*`, `app/tracing/*`).

## Contracts & API structure

Wire type names below are owned by contracts-foundation's `chat-wire-api` capability; the
orchestrator imports them and never redefines. Where a concrete name is inferred, it is marked
`[CONFIRM]` against the frozen contract.

### `POST /api/chat/session` — bootstrap

- **Request** `SessionContext` (from URL query params): `{ userId: str, sessionId: str,
  accessToken: str (JWT), isDarkTheme: bool, platform: "web"|"app", page: str }`.
- **Response** `ChatBootstrapResponse` `[CONFIRM]`: `{ thread_id: str, client_id_display: str,
  entry_surface: "support"|"reports", blocks: RenderBlock[] (a greeting `BotBubble` + a
  `ChipRow` of entry chips), disclaimer: str ("Factual answers only — never investment
  advice.") }`.
- **Auth/error**: JWT validated server-side; `client_id` derived from the session claim, never
  from `userId` in the body if it disagrees. `401` on invalid/expired JWT (the only non-200
  path). No thread state persisted for a rejected bootstrap.

### `POST /api/chat` — one turn

- **Request** `ChatTurnRequest` `[CONFIRM]`: `{ thread_id: str, input: TurnInput }` where
  `TurnInput` is one of `{ text: str }` (free text), `{ chip: ChipAction }` (quick-reply /
  recovery chip tap), `{ stepper: StepperInput }` (stepper-card step selection), or
  `{ calendar: DateSelection }` (in-chat calendar pick). Session re-validated via the same
  JWT (header or re-sent `SessionContext`).
- **Response** `ChatTurnResponse` `[CONFIRM]`: `{ thread_id: str, turn_number: int,
  conversation_state: "open"|"soft_closed", follow_up_count: int, blocks: RenderBlock[] }`.
  `RenderBlock` = the frozen union: `BotBubble | UserBubble | ChipRow | StepperCard |
  CalendarBlock | FileCard | NoteListCard | DataCard | ErrorBubble | TicketConfirmation`.
- **Error behavior**: all conversational failures are **in-band** (HTTP 200 + an `ErrorBubble`
  from `error-taxonomy`: `E-NODATA` / `E-YEAR` / `E-TIMEOUT` / `E-FETCH` / `E-UNKNOWN`, copy +
  recovery chips verbatim per §8.4). `Reason`/HTTP codes/URLs never reach the body (logged
  server-side only). `401` only for auth failure.

### Internal orchestration surface (`app/orchestrator/`)

- `bootstrap_session(ctx: SessionContext) -> ChatBootstrapResponse` — greeting + entry-chip
  assembly; `thread_id = uuid4()`.
- `@observe(type="agent") async handle_turn(req: ChatTurnRequest) -> ChatTurnResponse` — the
  root trace span; calls `update_current_trace(thread_id, user_id, metadata={turn_number,
  model_version})` (via the tracing helper) and orchestrates the pipeline. Branches on input
  kind: **free-text → `run_agentic_loop`**; **structured event → `dispatch_event`** (no LLM).
- `async run_agentic_loop(text: str, state: ThreadState) -> TurnResult` — the native tool-use
  loop: Claude call (`llm-client`) with `tools=<frozen registry>`; explicit `while` over
  `stop_reason` (iterations `< 3`): `tool_use` → execute every block server-side via the
  registry binding, append the assistant content blocks + a **single** user turn carrying all
  `tool_result` blocks (each matching its `tool_use_id`; failed execution → `is_error: true`,
  never dropped), re-call; `pause_turn` → re-send + continue; `end_turn` → break; `refusal` →
  escalation chips. Inputs are `strict`-validated by the API, so no tool-arg re-validation —
  only the `client_id` session binding is checked. On the cap → escalate to ticket/call chips.
  Returns the final text + the tool-assembled render blocks.
- `dispatch_event(input: TurnInput, state: ThreadState) -> TurnResult` — deterministic path for
  structured UI events (chip/calendar/stepper), driving the flow-engine directly; **also** the
  path for a router-forced intent whose params are incomplete (opens/advances the stepper). No
  Claude call.
- **Frozen tool registry** (`app/contracts/tools.py`, contracts-foundation) + orchestrator
  bindings (frozen contracts / published entrypoints; fakes in tests):
  - `route` — the router tool (`router-contract`: `Intent`, `ExtractedParams`, `RouterResult`).
  - `get_*_report` (per-flow report tools) → `engine.step(flow_state: FlowState | None,
    intent: Intent, params: ExtractedParams, input: TurnInput) -> StepResult(blocks,
    next_state)` (`flow-engine-contract`).
  - `search_kb` → `rag.answer(query: str, history: list[Turn]) -> RagResult(blocks,
    retrieval_context)` (rag-service #4 entrypoint).
  - `raise_ticket` / `get_ticket_status` → `ticketing.*` (ticketing #12), e.g.
    `ticketing.raise_ticket(thread_id, transcript) -> TicketConfirmation`.
  - `store.enqueue(record: TurnRecord) -> None` (store-writer #13; non-blocking) — fan-out, not
    a Claude tool.
- `SessionStateStore` — `get(thread_id) -> ThreadState | None`, `put(thread_id, state)`;
  Phase-1 in-memory dict.

## Dependencies & contracts consumed

- **Frozen contracts imported** (never edited): `chat-wire-api` (SessionContext + all render
  blocks + request/response), the **frozen tool registry** `app/contracts/tools.py`
  (`route`/`get_*_report`/`search_kb`/`raise_ticket`/`get_ticket_status` — the tool schemas
  passed to Claude), `router-contract` (Intent/ExtractedParams/RouterResult),
  `flow-engine-contract` (FlowState/Step/StepResult), `remote-config` (greeting pool, per-entry
  chip sets, limits: message cap 10, follow-up cap 2, page size 10), `error-taxonomy` (E-*
  codes/copy/chips), `tracing-conventions` (`@observe` types, `configure_tracing`, thread
  stitch), `conversation-store` (`TurnRecord` handed to `enqueue`), `llm-client`.
- **Must land first**: contracts-foundation (#0).
- **Parallel-safe**: flow-engine (#2), llm-router (#3), rag (#4), ticketing (#12), store-writer
  (#13), tracing (#14) — consumed via interfaces/entrypoints with in-memory fakes until they
  merge; integration tests then swap the reals in.
- **Cross-change wiring note**: store-writer and tracing expose startup/shutdown + per-turn
  hooks that **only this change** calls from `app/main.py`; their proposals must not edit
  `app/main.py`.

## Done condition & test command

Done when: `POST /api/chat/session` returns a time-correct greeting + the correct entry
surface's chips from remote-config; `POST /api/chat` runs a full turn against in-memory fakes,
routing free-text turns through the agentic loop and structured events through the deterministic
path, emitting only valid `chat-wire-api` blocks; the **agentic loop executes a faked
`tool_use` → `tool_result` → follow-up cycle correctly** (`tool_use_id` matched on the appended
`tool_result`, ≤3 iterations enforced then escalation, and the fulfilment output comes from the
tool result — never from Claude prose); a **parallel `tool_use` fixture (two `tool_use` blocks
in one assistant message) proves both results return in a single user message**, and a failed
tool execution returns `is_error: true` rather than being dropped; structured UI events drive
the engine with **no** Claude call; the 10-message soft close, ≤2-follow-up escalation, and
sticky-language rule are enforced;
`thread_id` is generated once and echoed every turn; `store.enqueue` and the tracing root span
are invoked (asserted via fakes) without the response awaiting the DB write; `client_id` is
taken from the session, never the request body.

`pytest tests/orchestrator/` green — fixture/fake-based, **no live FinX/Freshdesk, no DB, no
real LLM call**.
