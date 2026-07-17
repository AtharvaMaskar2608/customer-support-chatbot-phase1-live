# loop.md — conversation-store-writer

Worktree lead loop state. If it isn't here, it didn't happen.

Branch: `conversation-store-writer` (off main @ cfb22a1)
testCommand: `pytest tests/store/`
doneCondition: see manifest.yaml (ordering/non-blocking, full-column insert,
forced-error + queue-full log-and-drop, start/stop drain, 0002 applies on 0001).

## Contract reconciliation (frozen contracts override proposal prose)

The proposal predates the frozen contracts-foundation surface (landed @ cfb22a1).
Where prose and the frozen contract disagree, the frozen contract wins (CLAUDE.md
frozen surface). Reconciliations, all confirmed against the landed code:

1. **Table name.** Prose says `conversation_turns`; the frozen `0001` migration
   creates `turns` (+ parent `threads`). Insert into `turns`.
2. **Token columns.** Prose says `input_tokens`/`output_tokens`; the frozen
   `TurnRecord` DTO + `0001` use `prompt_tokens`/`completion_tokens`. Use the DTO.
3. **DB driver.** Prose `__init__` says `asyncpg.Pool | ConnectionFactory`; the
   frozen `db-config` (`app/config/db.py`) provides a **psycopg 3 async**
   connection factory (`session_factory(engine) == engine.connection`, an async
   context manager yielding `psycopg.AsyncConnection`). Build against the psycopg
   async connection factory (the `ConnectionFactory` arm); no asyncpg.
4. **user_id / FK / threads upsert.** `user_id` is a required `TurnRecord` field
   but has NO column on `turns` — it lives on `threads`, and `turns.thread_id`
   has a FK to `threads(thread_id)`. To persist the full TurnRecord (done
   condition: "every required §3.2 column populated", incl. user_id) AND satisfy
   the FK, `_insert_turn` upserts the `threads` row (`ON CONFLICT (thread_id) DO
   NOTHING`, carrying user_id + model_version) before inserting the turn. This is
   required by the frozen schema, not scope creep — [CONFIRM] raised to team lead.
5. **0002 content.** `0001` already ships a NON-unique `(thread_id, turn_number)`
   index (idx_turns_thread_id_turn_number). So 0002 adds the write-side
   **idempotency guard**: a UNIQUE index on `(thread_id, turn_number)`, which is
   both the "cheap per-thread read-back" key and the re-enqueue idempotency guard
   the proposal names. Additive, forward-only, does not edit 0001. No retry/DLQ
   table (log+drop).

## Tasks completed
- (none yet)

## Current task
- Task 1: scaffolding (tasks.md + loop.md) — IN PROGRESS (this commit).

## Verifier rounds
- (none yet)

## Open questions / escalations
- [CONFIRM] threads upsert in _insert_turn (reconciliation #4). Proceeding: it is
  the only way to satisfy the done condition against the frozen FK schema.
