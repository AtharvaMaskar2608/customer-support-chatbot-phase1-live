# Tasks: conversation-store-writer

Implementation order (each task = one commit). Tests are written from this
proposal, not from the implementation.

## 1. Scaffolding — tasks.md + loop.md
- [ ] Author this task list and the loop.md loop-state file, recording the
      prose↔frozen-contract reconciliation decisions (see loop.md "Contract
      reconciliation").

## 2. Migration 0002 — write-side idempotency guard
- [ ] `app/store/migrations/0002_turns_idempotency_guard.sql`: additive,
      forward-only. Add a UNIQUE index on `turns (thread_id, turn_number)` — the
      write-side guard the writer's `ON CONFLICT` re-enqueue idempotency needs.
      Never edits `0001`; the runner (read-only to this change) applies it.

## 3. Writer module — `app/store/writer.py`
- [ ] `ConversationStoreWriter`: bounded `asyncio.Queue` + single background
      worker with its own DB connection (from the consumed connection factory).
- [ ] `enqueue(record)` — non-blocking `put_nowait`; on `QueueFull` → log +
      `store_write_dropped` metric + drop (identifiers only, never message PII);
      never raises into the caller.
- [ ] `start()` / `stop()` — spawn the worker; drain-then-cancel on stop. These
      are the lifespan hooks main.py (orchestrator-owned) calls.
- [ ] `_worker()` — `await queue.get()` → `_insert_turn`; any exception →
      log + metric + drop, continue; `task_done()` each item.
- [ ] `_insert_turn(record)` — one transaction: upsert the parent `threads` row
      (carries `user_id`, satisfies the FK) then insert one `turns` row with every
      §3.2 column; `ON CONFLICT (thread_id, turn_number) DO NOTHING` for
      re-enqueue idempotency (matches the 0002 unique index).

## 4. Tests — `tests/store/`
- [ ] Non-blocking ordering: `enqueue()` returns before the insert runs.
- [ ] Full-column insert: every §3.2 column populated (threads upsert + turns
      insert), asserted against a fake async connection double.
- [ ] Forced insert error → log-and-drop, worker survives, caller never sees it.
- [ ] Queue-full → log-and-drop, `enqueue` never raises, metric increments.
- [ ] `start()`/`stop()` drain queued records then shut down cleanly.
- [ ] Migration: `0002` discovered after `0001`, applies on top (dry-run parse —
      no live DB), unique-index guard present.
