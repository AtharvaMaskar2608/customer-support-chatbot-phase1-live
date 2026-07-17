-- 0001_conversation_store.sql
-- Conversation store: one row per conversation (threads) and one row per turn
-- (turns), written after every bot response. Captures decisions and tool traces
-- (not only the final text) to serve the 10-message cap and future fine-tuning.
-- Forward-only; no destructive statements. Applied by app/store/migrations/runner.py.

CREATE TABLE IF NOT EXISTS threads (
    thread_id      UUID PRIMARY KEY,
    user_id        TEXT        NOT NULL,          -- Client ID, e.g. X008593
    platform       TEXT,
    page           TEXT,
    entry_surface  TEXT,                          -- support | reports
    model_version  TEXT,
    status         TEXT        NOT NULL DEFAULT 'active',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id            UUID PRIMARY KEY,
    thread_id          UUID        NOT NULL REFERENCES threads(thread_id),
    turn_number        INTEGER     NOT NULL,      -- incrementing; serves the 10-message cap
    user_message       TEXT,
    assistant_message  TEXT,
    detected_intent    TEXT,
    extracted_params   JSONB,
    tool_calls         JSONB,                     -- name + args + results
    retrieval_context  JSONB,                     -- canonical list[str]
    render_blocks      JSONB,
    latency_ms         INTEGER,
    prompt_tokens      INTEGER,
    completion_tokens  INTEGER,
    model_version      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Retrieve a conversation's turns in order.
CREATE INDEX IF NOT EXISTS idx_turns_thread_id ON turns (thread_id);
CREATE INDEX IF NOT EXISTS idx_turns_thread_id_turn_number ON turns (thread_id, turn_number);
