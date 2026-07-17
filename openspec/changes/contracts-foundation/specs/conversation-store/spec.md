## ADDED Requirements

### Requirement: Threads table

The system SHALL define a `threads` table persisting one row per conversation,
created by migration `0001`. It SHALL carry `thread_id` (UUID primary key),
`user_id` (Client ID), `platform`, `page`, `entry_surface`, `model_version`,
`status`, `created_at`, and `updated_at`. `thread_id` SHALL be generated once per
session and reused to stitch that session's turns and traces.

#### Scenario: One thread row per conversation

- **WHEN** a new conversation starts
- **THEN** a `threads` row SHALL be created with a UUID `thread_id`, the Client ID as `user_id`, and the entry surface recorded

### Requirement: Turns table captures decisions and tool traces

The system SHALL define a `turns` table persisting one row per turn, created by
migration `0001`, written after every bot response. It SHALL carry `turn_id`
(UUID primary key), `thread_id` (foreign key to `threads`), `turn_number`
(integer), `user_message`, `assistant_message`, `detected_intent`,
`extracted_params` (JSONB), `tool_calls` (JSONB — name, args, and results),
`retrieval_context` (JSONB/text array), `render_blocks` (JSONB), `latency_ms`,
`prompt_tokens`, `completion_tokens`, `model_version`, and `created_at`. The
schema SHALL capture decisions and tool traces, not only the final text, to serve
future fine-tuning.

#### Scenario: Turn row records the full trace

- **WHEN** a bot response is persisted
- **THEN** the `turns` row SHALL record the detected intent, the extracted params, the tool calls with their args and results, the retrieval context, and the token/latency usage — not only the assistant text

#### Scenario: Turn number serves the message cap

- **WHEN** turns accumulate in a thread
- **THEN** each turn SHALL carry an incrementing `turn_number` so the 10-message conversation cap can be enforced from stored state

### Requirement: Indexing and referential integrity

The system SHALL index `turns` by `thread_id` and by `(thread_id, turn_number)`,
and SHALL enforce the `turns.thread_id` → `threads.thread_id` foreign key, so a
conversation's turns are retrievable in order.

#### Scenario: Turns retrievable in order

- **WHEN** a conversation's history is read
- **THEN** the `(thread_id, turn_number)` index SHALL allow retrieving that thread's turns in turn order

### Requirement: Forward-only numbered migration convention

The system SHALL apply migrations as forward-only, numbered SQL files
(`NNNN_description.sql`) tracked in a `schema_migrations` table by a runner. This
change SHALL own `0001_conversation_store.sql`; subsequent migrations
(`0002` onward) SHALL be owned by the conversation-store-writer change. The runner
SHALL apply only not-yet-applied files, in numeric order.

#### Scenario: Runner applies pending migrations in order

- **WHEN** the migration runner executes
- **THEN** it SHALL apply each un-applied `NNNN_*.sql` file in ascending numeric order and record it in `schema_migrations`

#### Scenario: Already-applied migration is skipped

- **WHEN** the runner re-runs after `0001` has been applied
- **THEN** it SHALL skip `0001` and apply only later un-applied files

### Requirement: TurnRecord producer/consumer DTO

The system SHALL define a frozen `TurnRecord` Pydantic DTO in a contracts module
(`app/contracts/store.py`) that mirrors the `turns`/`threads` columns of migration
`0001`: `thread_id`, `turn_id`, `user_id`, `user_message`, `assistant_message`,
`intent`, `tool_calls` (name + args + results), `retrieval_context` (the canonical
`list[str]` shape), timestamps, latency and token usage, `model_version`, and
`turn_number`. `TurnRecord` SHALL be the single shared shape between the producer
(the orchestrator, which enqueues a `TurnRecord` after each bot response) and the
consumer (the store-writer, which inserts it), so neither side redefines the row.

#### Scenario: Producer and consumer share one shape

- **WHEN** the orchestrator enqueues a completed turn and the store-writer inserts it
- **THEN** both SHALL use the same `TurnRecord` DTO, whose fields correspond one-to-one with the `0001` columns

#### Scenario: retrieval_context uses the canonical shape

- **WHEN** a `TurnRecord` carries retrieval context
- **THEN** it SHALL use the canonical `retrieval_context: list[str]` shape from the RAG contract, not a store-local shape
