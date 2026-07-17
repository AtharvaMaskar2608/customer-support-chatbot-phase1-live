## ADDED Requirements

### Requirement: Typed span taxonomy

The system SHALL define a span taxonomy with four typed spans — `agent`,
`retriever`, `llm`, and `tool` — matching the DeepEval `@observe(type=...)`
convention. Every observed span SHALL set its `type`, because typed spans unlock
component-specific metrics. The canonical shape SHALL be a root `agent` span
(answer-user-query) wrapping a `retriever` span (retrieve-context) and an `llm`
span (generate-response), with `tool` spans for FinX/Freshdesk calls.

#### Scenario: Every span carries a type

- **WHEN** a span is opened
- **THEN** it SHALL declare one of `agent` / `retriever` / `llm` / `tool` as its type

#### Scenario: Retriever span carries retrieval context

- **WHEN** a `retriever` span is recorded for a RAG turn
- **THEN** it SHALL carry the per-turn `retrieval_context` using the canonical `list[str]` shape defined in the RAG contract (`app/contracts/rag.py`), which is required for RAG metrics

### Requirement: Tracing setup contract

The system SHALL define the `trace_manager.configure(...)` setup contract with
parameters `openai_client`, `confident_api_key`, `environment`
(`development`/`staging`/`production`), `sampling_rate` (default 1.0), and `mask`
(a PII-redaction hook). Confident AI export SHALL be optional (tracing works fully
offline). The contract SHALL note that the installed DeepEval `configure()`
signature documents only `openai_client`; if the version lacks an Anthropic
auto-patch hook, Claude calls SHALL be logged manually on the `llm` span.

#### Scenario: Configure accepts the documented parameters

- **WHEN** tracing is initialized
- **THEN** `configure` SHALL accept `openai_client`, `confident_api_key`, `environment`, `sampling_rate`, and `mask`, and SHALL function without a Confident AI key

### Requirement: PII masking hook

The system SHALL define a `mask` function signature applied to trace data before
any export. The `mask` hook SHALL redact names, emails, Client IDs, and ledger
amounts. The get-profile full response (heavy PII) SHALL never be logged, stored,
traced, or sent to the client — only the extracted first name is retained in
memory for the greeting.

#### Scenario: Mask redacts PII before export

- **WHEN** trace data is exported
- **THEN** the `mask` hook SHALL redact names, emails, Client IDs, and ledger amounts first

#### Scenario: get-profile PII is never traced

- **WHEN** get-profile returns the full profile object
- **THEN** the backend SHALL extract only `FirstHolderName` → first name and SHALL NOT log, store, trace, or return the rest

### Requirement: Thread-based multi-turn stitching

The system SHALL define multi-turn tracing as per-turn traces stitched by a shared
`thread_id` generated once per session (uuid4) and persisted alongside history,
using `update_current_trace(...)`. Conversation state SHALL be the app's
responsibility; DeepEval only observes. The contract SHALL record the production
rule that local LLM-judge metrics are never run in production (blocking latency);
`metric_collection` is used for async evaluation, and long-running servers
periodically clear traces.

#### Scenario: Turns stitched by thread_id

- **WHEN** multiple turns occur in one session
- **THEN** each turn's trace SHALL carry the same `thread_id` so they group into one conversation

#### Scenario: No blocking judge metrics in production

- **WHEN** running in the production environment
- **THEN** local LLM-judge metrics SHALL NOT run inline; async metric collection SHALL be used instead
