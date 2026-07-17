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
- Task 1 (46bb14f): tasks.md + loop.md scaffolding.
- Task 2 (419fbaa): migration 0002 — UNIQUE (thread_id, turn_number) idempotency
  guard. Dry-run parse: runner discovers 0002 after 0001; pending after 0001.
- Task 3 (e1ff880): app/store/writer.py — ConversationStoreWriter (bounded queue,
  single worker w/ own connection, non-blocking enqueue, start/stop drain,
  _insert_turn = threads upsert + turns insert, log-and-drop policy).
- Task 4 (15bf3d7): tests/store/ — 14 tests, all done-condition promises. Written
  from the spec. testCommand `pytest tests/store/` = 14 passed. Full `pytest` = 96
  passed (baseline was 82).

## Post-verify hardening (committed 3e25870)
Before verification a hardening pass was in the working tree; reviewed in the
lean self-check (below), found sound and spec-aligned, and committed:
- Worker opens ITS OWN dedicated DB connection once and reuses it across turns
  (matches the proposal's "single background worker, its own DB connection"),
  instead of a fresh connection per insert. On any insert failure the connection
  is discarded so the next record reconnects — an aborted transaction never leaks
  into the following turn. `_close_cm` swallows close errors so releasing a broken
  connection can never kill the worker.
- `_safe_drop` wraps log-and-drop so even a malformed (non-`TurnRecord`) enqueued
  object cannot raise into the worker loop; `_drop` reads identifiers via getattr.
- `stop()` races `queue.join()` against the worker task (FIRST_COMPLETED) so a
  lifespan shutdown cannot hang if the worker has already exited.
- Tests +4 (conn reused across turns; reconnect after insert error; factory-open
  failure contained; stop no-hang guard). tests/store = 18 passed.

## Verification — LEAN PASS (single self-check)
Per the team lead's LEAN DIRECTIVE (human operator asked to cut verifier-agent
overhead and trust implementations): NO 3-lens fresh-verifier panel this pass.
Instead one worktree-lead self-check against proposal.md/tasks.md/manifest.yaml +
`git diff main...HEAD`, looking ONLY for blocking issues.
- Result: 0 blocking issues.
  - All touched files inside the manifest (writer.py, migrations/0002_*,
    tests/store/**, this change's openspec dir). No edits to frozen contracts
    (0001, app/contracts/store.py, app/config/db.py, app/main.py) or the runner.
  - Writer `INSERT INTO turns` lists exactly the 15 frozen-0001 `turns` columns in
    order; `_turn_params` supplies 15 values in the same order; `threads` upsert
    satisfies the NOT NULL user_id FK parent; `intent.value` -> detected_intent;
    JSONB columns wrapped in `Jsonb`.
  - 0002 creates exactly the UNIQUE (thread_id, turn_number) index the writer's
    `ON CONFLICT` arbiter requires; additive, forward-only, never edits 0001.
  - doneCondition items all covered by tests (ordering/non-blocking, full-column
    insert, forced-error + queue-full log-and-drop, start/stop drain, 0002 on 0001).

## Integration (origin/main @ b727d53)
Orchestrator (PR #4) is on main and is the sole caller. It depends only on the
`enqueue(record: TurnRecord) -> None` PORT (app/orchestrator/ports.py) and ships a
default in-memory stand-in (app/orchestrator/defaults.py); it does NOT import
`ConversationStoreWriter`. This writer satisfies that port 1:1. No main.py edit is
owed by this change (the orchestrator owns main.py / lifespan wiring).

## Rebase + behavior harness
- Rebased conversation-store-writer onto origin/main @ b727d53 (contains PR #2
  finx-http-adapters, #3 flow-brokerage, #4 conversation-orchestrator, #5
  flow-contract-notes). Clean — zero file overlap, no conflicts.
- testCommand `pytest tests/store/` = 18 passed on the rebased head.
- Full behavior harness `uv run pytest -q` = 248 passed on the rebased head.
- Evals (DeepEval) / `/qa` NOT run: this change touches no chat behavior or UI
  (pure backend persistence writer), so the CLAUDE.md trigger does not apply.

## Final metrics
- Verifier rounds: 0 panels (lean directive; 1 self-check pass, 0 blocking issues).
- Escalations: 0.
- doneCondition: satisfied. testCommand: green (18). Behavior harness: green (248).

## Open questions / escalations
- [CONFIRM] threads upsert in _insert_turn (reconciliation #4) — RESOLVED, carried
  forward. It is the only way to persist the full TurnRecord (user_id) and satisfy
  the frozen FK; the self-check confirmed it against the frozen 0001 schema. Not
  scope creep — required by the frozen schema.

## Status
- SHIPPED — PR pending link (filled after `gh pr create`).
