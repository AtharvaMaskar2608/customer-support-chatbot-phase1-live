# Proposal: conversation-store-writer

## Why

`02_technical_spec.md` §2.3 step 7 and §3.2 require that **after every bot response a separate
thread inserts the turn into PostgreSQL** — capturing not just the final text but the decisions
and tool traces (intent, tool calls + args + results, retrieval context, latency/token usage,
model version, turn number) to serve future fine-tuning. Contracts-foundation defines the
conversation-store schema and its `0001` migration; this change is the **writer** that fills it.

The hard constraint is decoupling: the user-facing latency must **never** wait on this write.
Live conversation state is the orchestrator's in-process store; this table is async, write-only
analytics/fine-tuning capture. A dropped row degrades the training corpus, not the conversation.
This change is the **sole owner of migrations `0002+` after contracts-foundation lands** (map
row 13).

## What Changes

- **Non-blocking write path** — a `ConversationStoreWriter` with a bounded in-process queue and
  a single background worker (its own DB connection), started/stopped in the FastAPI lifespan.
  The orchestrator calls `enqueue(record)`, which returns immediately; the worker drains the
  queue and performs the insert off the request path. No `await` on the DB ever reaches the turn
  response.
- **One row per turn** — the worker inserts a `TurnRecord` into `conversation_turns` with every
  §3.2 column: `thread_id`, `turn_id`, `user_id` (Client ID), user message, assistant message,
  detected intent, tool calls + args + results, retrieval context, timestamps, latency + token
  usage, model version, and turn number.
- **Write-failure policy — LOG + DROP (chosen)** — on queue-full or insert error, log the
  exception plus the dropped `thread_id`/`turn_id` (identifiers only, never message PII) and a
  `store_write_dropped` metric, then drop. Rationale: this data is best-effort and fully
  decoupled from correctness; a durable retry queue is deferred to Phase 2 (would require its own
  table and a redelivery loop — explicitly **not** built now). This keeps the writer stateless
  and failure-isolated.
- **Migrations `0002+`** — reserved and solely owned here. Phase-1 `0002` adds the write-side
  index/constraint the writer needs (a `(thread_id, turn_number)` index for cheap per-thread
  read-back and an idempotency guard on re-enqueue). No retry-queue table (log+drop). The base
  `conversation_turns`/threads DDL stays in contracts-foundation `0001` — this change never edits
  `0001`.

## Capabilities

### New Capabilities

- `conversation-store-writer`: the async, non-blocking persistence path — `enqueue()` +
  background worker that inserts one fully-traced turn row per bot response into
  `conversation_turns`, with a log-and-drop failure policy and the `0002+` write-side migrations.

### Modified Capabilities

- `conversation-store` (contracts-foundation): **consumed, not modified** — the writer inserts
  into the frozen schema and imports the `TurnRecord` model; it does not alter the `0001`
  migration or the table's base shape.

## Impact

- **New code**: `app/store/writer.py` (the writer, queue, worker, insert) and
  `app/store/migrations/0002_*` (write-side index/constraint).
- **APIs**: internal only — `ConversationStoreWriter.enqueue()` / `start()` / `stop()`; no HTTP
  surface. No FinX/Freshdesk contact.
- **Downstream/dependencies**: depends on contracts-foundation (#0); runs in parallel with the
  orchestrator (#5), which is the sole caller of `enqueue()` and the sole editor of
  `app/main.py` (this change exposes lifecycle hooks but never edits `main.py`).
- **Out of scope**: no live-state / read serving (that's the orchestrator's in-memory store), no
  Postgres read APIs for analytics, no retry/DLQ table, no schema for RAG `qa_chunks` (separate,
  pre-existing).

## Files touched

Exclusive to this change (map row 13) — nothing outside it:

- `app/store/writer.py` — the writer (queue, worker, `enqueue`, `_insert_turn`, lifecycle).
- `app/store/migrations/0002_*` (+ any later `0003…`) — **sole migration owner post-contracts.**
- `tests/store/**` — writer unit/integration tests.

Untouched: `app/store/migrations/0001_*` and the `conversation-store` schema (owned by
contracts-foundation), `pyproject.toml`/lockfile, root config, `app/main.py` (orchestrator owns
it — this change only exposes `start()`/`stop()`/`enqueue()` for it to call).

## Contracts & API structure

### `class ConversationStoreWriter` (`app/store/writer.py`)

- `__init__(self, pool: asyncpg.Pool | ConnectionFactory, queue_maxsize: int = 1000)`
- `async def start(self) -> None` — spawn the background worker task (called from the
  orchestrator's FastAPI lifespan startup).
- `async def stop(self) -> None` — drain-then-cancel the worker, close resources (lifespan
  shutdown).
- `def enqueue(self, record: TurnRecord) -> None` — **non-blocking**; `put_nowait` onto the
  bounded queue. On `QueueFull` → log + drop (never raises into the caller). This is the sole
  integration point with the orchestrator.
- `async def _worker(self) -> None` — loop: `await queue.get()` → `await _insert_turn(record)`;
  any exception → log (`thread_id`/`turn_id` + error) + drop, continue.
- `async def _insert_turn(self, record: TurnRecord) -> None` — single `INSERT INTO
  conversation_turns (...)`.

### `TurnRecord`

Consumed from contracts-foundation's `conversation-store` capability — **not redefined here**.
Fields (mirroring the §3.2 / `0001` table columns): `thread_id: str`, `turn_id: str`,
`user_id: str`, `user_message: str`, `assistant_message: str` (or the render-block payload),
`intent: Intent`, `tool_calls: list[ToolCallRecord]` (`{name, args, result}`),
`retrieval_context: list[str]`, `created_at: datetime`, `latency_ms: int`, `input_tokens: int`,
`output_tokens: int`, `model_version: str`, `turn_number: int`.

`[CONFIRM]` — `TurnRecord` must live in contracts-foundation (shared by the orchestrator as
producer and this writer as consumer). If contracts-foundation ships only the `0001` DDL and no
DTO, that model has no single owner and the two changes will collide defining it — see the
conflict note in the return.

### Table `conversation_turns`

DDL owned by contracts-foundation `0001`. Columns per §3.2. This change adds only the `0002`
index `(thread_id, turn_number)` + idempotency guard; inserts, never alters the base table.

## Dependencies & contracts consumed

- **Frozen contracts imported**: `conversation-store` (`TurnRecord` model + `0001` schema),
  `router-contract` (`Intent` type on the record), DB connection config from `app/config`.
- **Must land first**: contracts-foundation (#0) — provides the schema, `TurnRecord`, and the DB
  config/pool convention.
- **Parallel-safe**: the orchestrator (#5). The integration contract between them is exactly the
  `enqueue(record: TurnRecord) -> None` signature + the shared `TurnRecord`; both consume
  `TurnRecord` from contracts-foundation, so there is no shared-file edit.

## Done condition & test command

Done when: `enqueue()` returns before the insert completes (proven by ordering assertion —
response path never blocks on the DB); the worker inserts a `TurnRecord` into `conversation_turns`
with every required §3.2 column populated; a forced insert error and a queue-full condition each
log-and-drop without raising into the caller; `start()`/`stop()` cleanly drain and shut down; the
`0002` migration applies on top of `0001`.

`pytest tests/store/` green — against a disposable Postgres (testcontainer / ephemeral schema
with `0001`+`0002` applied) or a fake connection double; **never the live/prod DB**.
