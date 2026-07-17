-- 0002_turns_idempotency_guard.sql
-- Write-side guard for the conversation-store writer (conversation-store-writer).
-- Forward-only; additive; no destructive statements. Applied by
-- app/store/migrations/runner.py (read-only to this change) on top of 0001.
--
-- 0001 already ships a NON-unique (thread_id, turn_number) index for per-thread
-- read-back. This adds the UNIQUE guarantee the writer needs: exactly one row per
-- (thread_id, turn_number), which is also the ON CONFLICT arbiter that makes a
-- re-enqueued turn a no-op instead of a duplicate row (the writer's idempotency
-- guard). No retry/DLQ table — the writer's failure policy is log-and-drop.

CREATE UNIQUE INDEX IF NOT EXISTS uq_turns_thread_id_turn_number
    ON turns (thread_id, turn_number);
