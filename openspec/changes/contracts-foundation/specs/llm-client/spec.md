## ADDED Requirements

### Requirement: Pinned model IDs with configurable toggle

The system SHALL define an LLM client wrapper over the Anthropic SDK that uses the
pinned model IDs: default `claude-sonnet-5` and a backend-configurable cheap-model
toggle `claude-haiku-4-5-20251001`. The active model SHALL be selected from
config, not hardcoded at the call site. These IDs replace the flow spec's
non-existent "sonnet-4-6".

#### Scenario: Default model is claude-sonnet-5

- **WHEN** the wrapper is invoked without a model override and no toggle is set
- **THEN** it SHALL call `claude-sonnet-5`

#### Scenario: Toggle selects Haiku from config

- **WHEN** the backend config sets the cheap-model toggle
- **THEN** the wrapper SHALL call `claude-haiku-4-5-20251001`

### Requirement: Thin wrapper with no business logic

The system SHALL define the wrapper to expose a single completion method that
accepts messages, an optional system prompt, and optional tools, and returns the
response text plus token usage (prompt and completion tokens). The wrapper SHALL
contain no prompt text, no routing logic, and no flow logic — those belong to the
router and RAG changes. The wrapper SHALL NOT send `temperature`, `top_p`, or
`top_k`, because `claude-sonnet-5` runs adaptive thinking by default and rejects
non-default sampling parameters.

#### Scenario: Wrapper returns text and usage

- **WHEN** the wrapper completes a request
- **THEN** it SHALL return the response text and the prompt/completion token counts for the conversation-store and tracing to record

#### Scenario: No sampling parameters sent

- **WHEN** the wrapper builds a request to `claude-sonnet-5`
- **THEN** it SHALL NOT include `temperature`, `top_p`, or `top_k`

### Requirement: Integrates with the tracing llm span

The system SHALL define the wrapper to attach the `llm` tracing span so model,
tokens, and messages are captured for every call, consistent with the tracing
conventions. Business callers SHALL depend only on the wrapper's completion method,
not on the raw Anthropic client.

#### Scenario: Calls are observed on the llm span

- **WHEN** the wrapper makes a model call
- **THEN** the call SHALL be recorded on an `llm`-typed tracing span with the model id and token usage

### Requirement: Native tool-use passthrough; no free-text JSON parsing

The wrapper SHALL pass `tools=`, `tool_choice=`, and `output_config.format` through
to the Anthropic SDK unchanged. Structured LLM outputs SHALL arrive only as
schema-validated `tool_use` blocks or `output_config.format` json_schema output.
The system SHALL NOT parse free-text JSON for any structured decision, anywhere.
The wrapper SHALL surface the response `stop_reason` (including `tool_use`,
`pause_turn`, and `refusal`) so the orchestrator can drive the agentic loop.

#### Scenario: Tools and tool_choice pass through

- **WHEN** the caller supplies `tools=` and `tool_choice=`
- **THEN** the wrapper SHALL forward them unchanged and return the `tool_use` blocks and `stop_reason` without post-processing the model text

#### Scenario: No free-text JSON parsing

- **WHEN** a structured decision is needed
- **THEN** it SHALL be obtained from a schema-validated `tool_use` block or `output_config.format` output, never by parsing free-text JSON from a text block
