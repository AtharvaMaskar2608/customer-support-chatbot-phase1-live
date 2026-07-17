## Context

Choice Jini is a post-login agentic support chatbot for FinX (Choice India's
trading platform): a React widget over a Python/FastAPI backend that fulfils 11
report flows deterministically and answers process questions via RAG. `CLAUDE.md`
forbids parallel fan-out until shared types/interfaces/API schemas land in `main`,
and `docs/technical/02_technical_spec.md` §9 names a contracts-first change as the
explicit next build step (build-readiness verdict READY-WITH-CAVEATS, 2026-07-16).

Today none of those contracts exist as code. This change lands **contracts plus
their thin enforcement code only** — typed models, three response-envelope
parsers with fixture tests, config schemas with defaults, one DB migration, an
LLM client wrapper, and a chat-endpoint stub. No flow logic, no router prompt, no
RAG retrieval, no widget UI. Downstream tasks (16 changes in the decomposition
map) import these contracts and are forbidden from editing the frozen surface
(Intent enum, `FinXClient` interface, remote-config schema).

All source facts here are grounded in `02_technical_spec.md` (all sections),
`03_finx_api_reference.md` (full), `04_freshdesk_api_reference.md` §0/§5,
`docs/finx_api_captures_2026-07-16.md`, and `docs/customer_support_chatbot_phase1.md`.

## Goals / Non-Goals

**Goals:**

- Define the widget↔backend wire contract, including the Phase-1 streaming
  decision, so the widget shell and orchestrator can build against a stable shape.
- Define the complete `Intent` enum and router I/O so flow tasks never re-invent it.
- Define a per-backend FinX adapter set covering all five hosts/auth schemes, the
  three response-envelope parsers, and typed request/response models per captured
  endpoint, with the 2026-07-16 captures as parser fixtures.
- Define the flow/step state-machine contract and its externalized guardrail
  config (date windows, FY math, byte-validation/retry/cache semantics).
- Land the conversation-store migration (single owner), the remote-config schema,
  tracing conventions, the error taxonomy, and the pinned-model LLM client wrapper.
- Establish a package skeleton and dependency set (declaring ALL backend deps up
  front) so no downstream task edits `pyproject.toml`/lockfile for a new dep.

**Non-Goals:**

- Any flow logic, router prompt, RAG retrieval, ticket-builder, tracing
  instrumentation, or widget component (owned by changes 1–16).
- Live FinX/Freshdesk calls or the real DB connection — parser/config tests are
  fixture-based and offline.
- Flows without captured file-delivery endpoints: Holding Statement and Global
  Detail delivery stay BLOCKED (owner decision, spec §9). Their intents exist as
  enum values so the router can classify them, but no fulfilment path is built.
- Resolving still-open API confirmations (MTF `Margin:1`, Holdings FINX-JWT
  provenance, SessionId lifetime). Contracts carry these as `[CONFIRM]`/`[GAP]`
  exactly as the source docs tag them.

## Decisions

### D1 — Chat wire protocol is non-streaming for Phase 1

One HTTP request per user turn returns **one JSON response** carrying an ordered
array of typed render blocks (bubble / user-bubble / chip-row / stepper-card /
calendar / file-card / note-list-card / data-card / error-bubble /
ticket-confirmation / generating). A `generating` indicator block covers the >5s
latency case (spec §8.2). The widget renders blocks in array order.

- **Rationale:** Phase-1 outputs are deterministic flow steps and short RAG
  answers, not long free-form generation. A turn is "collect a param" or "deliver
  a file card" — discrete, orderable blocks, not a token stream. Non-streaming
  keeps the widget renderer, the conversation-store writer, and DeepEval tracing
  each seeing one complete turn object, which is simpler to persist and score.
  File delivery is inherently non-streamable (backend fetches + byte-validates,
  then emits a card). The ">5s → Generating…" affordance gives the needed latency
  cover without SSE plumbing.
- **Alternatives considered:** SSE/token streaming (rejected — adds transport
  complexity for no product benefit at Phase-1 output sizes, and complicates
  single-turn persistence/tracing); WebSocket bidirectional (rejected — the widget
  is request/response per user action; no server-push requirement exists).
- **Constraint recorded for downstream:** flag any objection before deviating —
  the widget-shell and orchestrator changes both assume this shape.

### D2 — Per-backend adapter SET, not one FinX wrapper

The FinX surface spans **five hosts and several auth schemes** (spec §9,
`03` §1). One generic client cannot fit them. `app/finx/interfaces.py` defines a
Protocol per backend; `app/finx/adapters/**` (owned by change 1) implements them.
A `FinXClient` facade Protocol routes an endpoint to its adapter.

| Adapter | Host(s) / base path | Auth scheme | Endpoints |
|---|---|---|---|
| `DotNetMiddlewareAdapter` | `finx.choiceindia.com/api/middleware` | `authorization: <SessionId>` header **+ `SessionId` in body**; PascalCase | GetGlobalPNLPDF, GetLedgerDetailsPDF, GetTaxReportPDF, GetGlobalPNLNew, GetDetailedPNL, GetLedgerDetails |
| `GoMiddlewareAdapter` | `finx.` **and** `api.choiceindia.com/middleware-go` | `authorization` header only (contract list); `authorization: Session <SessionId>` prefix on `api.` download; get-brokerage-slab on `api.` uses SSO JWT; snake_case | report/contract (list), contract/download (bytes), v2/get-brokerage-slab |
| `MisReportsAdapter` | `finx.choiceindia.com/mis/reports` | `authType: jwt` + `authorization: <SSO JWT>` + `source: FINX_ANDROID`; camelCase | reports/generate (CML) |
| `MfProfileAdapter` | `mf.choiceindia.com/api/v2/investor/profile` | `authorization: <SSO JWT>` | extended (get-profile) |
| `FinxOmneCotiAdapter` | `finxomne.choiceindia.com/COTI/V1` | `authorization: Session <SessionId>` + `ssotoken: <SSO JWT>` header + FINX-issued JWT in body `accessToken` | Holdings |

- **Rationale:** casing (PascalCase / snake_case / camelCase), envelope shape,
  and credential routing all differ per backend. The widget forwards BOTH
  `sessionId` and `accessToken`; the adapter set routes the right credential to
  the right backend (`03` §1: "CML fails if handed the SessionId"). Encoding this
  as distinct adapters makes each backend's traps local and testable.
- **Alternatives considered:** single wrapper with per-call flags (rejected —
  produces a combinatorial mess of casing/auth branches and defeats per-endpoint
  typing); auto-negotiation from a URL (rejected — auth scheme is not derivable
  from the URL; e.g. `api.` host serves both SessionId and JWT endpoints).
- **`from:` header:** a build tag, not auth and not a source router (`03` §1
  live-tested). Adapters send one stable Jini value; do not build
  source-specific endpoints.
- **Auth-failure detection:** by transport **HTTP 401**, before envelope parsing.
  The two 401 envelopes (`.NET` vs MIS) differ (`03` §7). Go contract endpoint
  enforces no auth (FLAG A) — the backend MUST gate `client_id` by the widget's
  authenticated session; never proxy a user-supplied one.

### D3 — Three response-envelope parsers

`app/finx/envelopes.py` provides three pure parsers, each returning a normalized
`ParsedEnvelope{outcome: success|no_data|auth_error|error, payload, reason}`:

1. `parse_dotnet_envelope` — `{Status, Response, Reason}` (PascalCase). Success:
   `Status == "Success"`. No-data: `Status == "Fail"` and `Reason` in the
   no-data set (`"Data not found."` / `"Data not available."` — do NOT match a
   single literal; wording differs per endpoint, `03` §4.5). `Response` is
   **polymorphic**: URL string, confirmation string, array, object, or null.
2. `parse_go_envelope` — `{StatusCode, Message, DevMessage, Body}`. Success:
   `StatusCode == 200`. No-data: `StatusCode == 204`, `Body == {}`.
3. `parse_mis_envelope` — camelCase `{statusCode, message, devMessage, body}`
   (CML). Success: `statusCode == 200`; auth failure body is
   `{"statusCode":401,...}` but detection is by HTTP 401.

The brokerage endpoint returns a **hybrid** envelope (`StatusCode` AND `Status`
AND `Response`/`Reason`, `03` §4.6c); it is parsed by `parse_dotnet_envelope`
keyed on `Status`, with a note in `models.py`. `parse_dotnet_envelope` therefore
SHALL tolerate **extra keys** (ignore a redundant `StatusCode`) rather than
exact-shape-reject, and SHALL treat `Response` as any of string / array / object /
null / **empty string** — the `.NET` 401 auth body uses `Response: ""` (empty
string, not null), so response models must not assume `Response` is `str | null`
only. This is what lets one PascalCase parser serve `.NET`, `mf.` profile, COTI
Holdings, AND the brokerage hybrid — three parsers still suffice; no fourth is
needed. Two-parsers-minimum is a hard rule (`02` §4.8 trap #2): never build one
generic parser.

### D4 — DB driver: `psycopg[binary]` (psycopg 3)

- **Rationale:** the stack has no ORM (contracts are Pydantic v2, not SQLAlchemy
  models), pgvector DDL is hand-written SQL, and the conversation-store writer
  runs on a **separate thread** after each bot response (spec §2.3/§3.2). psycopg 3
  serves both an async path (FastAPI request handlers, RAG retrieval) and a sync
  path (the writer thread, the migration runner) from **one** driver, with a
  first-class pgvector adapter (`pgvector.psycopg`). This avoids pulling a second
  driver just for the sync writer.
- **Alternative considered:** `asyncpg` (rejected — faster but async-only, so the
  sync writer thread and the migration runner would need a second driver or an
  event-loop shim; its custom type codecs also complicate pgvector registration).

### D5 — Migrations: plain forward-only SQL, not Alembic

Migrations live in `app/store/migrations/NNNN_description.sql`, applied by a tiny
runner (`app/store/migrations/runner.py`) that tracks applied files in a
`schema_migrations` table. This change owns `0001_conversation_store.sql` and the
runner; change 13 (conversation-store-writer) is the sole owner of `0002+`.

- **Rationale:** Alembic's value is autogenerate/branching against ORM models —
  there are no ORM models to introspect here, and pgvector column DDL is
  hand-written regardless. The ownership map already encodes a numeric,
  single-owner-per-file convention (`0001_*` here, `0002+*` for change 13); plain
  SQL matches it directly and keeps SQLAlchemy out of the dependency set.
- **Alternative considered:** Alembic (rejected — adds SQLAlchemy + migration
  env machinery with no models to justify it; forward-only numbered SQL is
  sufficient for a greenfield schema).
- **Ownership note (surface to lead):** the ownership map lists only `0001_*` for
  this change; the runner is a small shared prerequisite for applying any
  migration, so this change also introduces `runner.py`. Flagged so change 13
  treats the runner as read-only.

### D6 — Flows register via a discovery registry (no shared-file edits)

`app/contracts/flow.py` defines a `FlowSpec` protocol. Each flow module (changes
6–11) exposes a **module-level `FLOW: FlowSpec`** object and imports no registration
function; `app/flows/__init__.py` (owned by change 2, flow-engine-runtime)
auto-discovers modules via importlib and collects each module's `FLOW`, keyed by
`Intent`. No flow task ever edits a shared registry list, and there are no
registration imports (aligns with the parallelization plan Hard Rule 5).

- **Rationale:** CLAUDE.md forbids overlapping-file edits across parallel tasks; a
  hand-maintained registry list would be a merge-conflict magnet across the six
  flow changes. A module-level `FLOW` object that discovery reads keeps "add a
  flow" = "add a module" with no import-time side effects and no shared-file edit.
- This change defines only the *contract* (the `FlowSpec` protocol) in
  `app/contracts`; the importlib discovery and the `__init__.py` registry belong to
  change 2.

### D7 — Repo layout (exactly per the ownership map)

```
pyproject.toml                      # declares ALL backend deps + lockfile
app/
  __init__.py
  main.py                           # FastAPI app; POST /api/chat + session bootstrap STUBS
  contracts/
    __init__.py
    wire.py                         # chat req/resp + render-block union + session-seed config slice (chat-wire-api)
    router.py                       # Intent, Segment, ReportFormat, ExtractedParams, ConversationContext, RouterResult
    rag.py                          # RetrievedChunk, RagAnswer, canonical retrieval_context: list[str]
    store.py                        # TurnRecord DTO (mirrors 0001 columns; orchestrator→store-writer contract)
    tools.py                        # frozen native-tool-use definitions (route + get_* + search_kb + ticket tools)
    flow.py                         # FlowState, Step, transitions, FlowConfig, FY helpers (IMPLEMENTED), FlowSpec protocol (module-level FLOW)
    errors.py                       # ErrorCode enum + ErrorCopy config type (error-taxonomy)
    tracing.py                      # SpanType, mask signature, trace setup contract (tracing-conventions)
    schema/
      chat_wire.schema.json         # generated JSON Schema of the wire union (checked in; widget TS codegen source)
      tools.schema.json             # generated JSON Schema of all tool input_schemas (checked in; drift-tested)
  finx/
    __init__.py
    interfaces.py                   # 5 adapter Protocols + FinXClient facade Protocol
    envelopes.py                    # 3 parsers + ParsedEnvelope
    models.py                       # typed request/response models + EndpointSpec descriptors per endpoint
  llm/
    __init__.py
    client.py                       # pinned-model Claude client wrapper contract (llm-client)
  config/
    __init__.py
    schema.py                       # RemoteConfig Pydantic schema (remote-config; incl. RAG tunables)
    defaults.py                     # default values (limits, chips, greeting pool, whats_new, products, date windows, RAG tunables)
    db.py                           # shared async engine + session factory (qa_chunks read + conversation-store write)
  store/
    __init__.py
    schema.py                       # typed Thread/Turn row models (conversation-store)
    migrations/
      0001_conversation_store.sql
      runner.py
tests/
  contracts/                        # contract, config, schema, wire-schema-drift tests (this change)
  finx/                             # envelope-parser + endpoint-model tests
  fixtures/finx/                    # sanitized 2026-07-16 capture JSON
```

`.env.example` at the repo root carries `FRESHDESK_API_KEY`, `FRESHDESK_API_ROOT`,
and the DB/OpenAI/Anthropic keys (contracts-foundation owns root files so no
downstream task edits them). The Freshdesk **field mapping** is NOT created here —
it stays ticketing-owned at `app/ticketing/freshdesk.yaml`.

Downstream read-only shared surface (per ownership map): `app/contracts/*`,
`app/finx/interfaces|envelopes|models`, `app/config/*`, `app/llm/client.py`.

### D8 — Dependencies declared up front

`pyproject.toml` pins the full backend dependency set now, so no downstream task
edits the lockfile for a new dep:

- `fastapi`, `uvicorn[standard]` — HTTP surface.
- `pydantic` (v2) — all contract models (locked stack).
- `httpx` — async FinX/Freshdesk client transport (used by adapters, change 1; rag/ticketing HTTP calls).
- `anthropic` — Claude client (router/RAG generation; llm-client wrapper).
- `openai` — `text-embedding-3-large` query embeddings @3072 (RAG, change 4).
- `deepeval` — tracing + eval harness (changes 14, 16).
- `psycopg[binary]` + `pgvector` — DB driver + vector adapter (D4); the async engine/session factory lives in `app/config/db.py`.
- `pytest`, `pytest-asyncio`, `respx` — test runner + the single repo-wide httpx mock (chosen once here so adapters/ticketing/rag all use the same one; `respx` over `pytest-httpx` for its explicit route-assertion API).

`deepeval` + `pytest` + `respx` sit in a `dev`/`eval` extras group. Migration
tooling is plain SQL (D5) — no Alembic dependency. The DeepEval judge model
(change 16) is `claude-opus-4-8` via the existing `anthropic` SDK — no new
dependency, and separate from the llm-client wrapper's pinned
`claude-sonnet-5`/`claude-haiku-4-5-20251001` pair.

### D9 — LLM client wrapper: pinned models, no business logic

`app/llm/client.py` wraps the `anthropic` SDK with the pinned IDs: default
`claude-sonnet-5`, backend-configurable toggle `claude-haiku-4-5-20251001`
(spec §2.1, memory `architecture-decisions`). The wrapper exposes a single
completion method returning text + token usage; it selects the model from config,
attaches the tracing `llm` span, and contains **no** prompt, flow, or routing
logic (those live in changes 3/4). The wrapper passes `tools=`, `tool_choice=`,
and `output_config.format` through unchanged (native tool use + structured
non-tool outputs, D15); structured decisions arrive only as schema-validated
`tool_use` blocks or `output_config.format` json_schema output, never parsed from
free-text JSON. Because `claude-sonnet-5` runs adaptive thinking by default and
rejects non-default sampling params, the wrapper does not expose or send
`temperature`/`top_p`/`top_k`, omits the `thinking` parameter (adaptive by
default), and defaults `max_tokens` to ~16000 for non-streaming calls. Model IDs
verified current against the Anthropic model catalog.

### D10 — Config reaches the widget in the chat response, not a separate fetch

The widget's ONLY network surface is `POST /api/chat`. The system SHALL NOT expose
a separate remote-config endpoint for the widget. The first chat response (the
session seed) SHALL embed the client-relevant config slice — the entry chips, the
time-aware greeting, the client-facing limits, and `whats_new` — inside a typed
`config_slice` on the wire response. Server-only config (calendar bound math, RAG
tunables, Freshdesk mapping) SHALL NOT be sent to the client.

- **Rationale:** one round trip for the widget; the WebView/floating-window shell
  never needs a second origin call, and the config the widget sees is exactly the
  slice the backend chooses to expose. Keeps the widget's trust surface minimal.
- **Alternative considered:** a `GET /api/config` the widget polls (rejected —
  second network surface, cache-coherence between config and greeting, and it
  would leak server-only knobs unless carefully filtered anyway).

### D11 — Wire union has a checked-in generated JSON Schema with a drift test

`app/contracts/schema/chat_wire.schema.json` SHALL be the Pydantic
`model_json_schema()` dump of the chat wire union, checked in. A pytest SHALL
regenerate it and diff against the committed file so it cannot silently drift. The
widget change (15) generates its TypeScript types from this file.

- **Rationale:** the widget is a separate package in a different language; a
  checked-in schema with a drift guard is the contract seam that lets TS types and
  Python models stay in lockstep without the widget importing Python.
- **Alternative considered:** hand-authored TS interfaces in the widget (rejected —
  drifts from the Python source with no guard).

### D12 — `app/main.py` is stub-here, orchestrator-owned thereafter

This change writes the `app/main.py` stub (FastAPI app + `POST /api/chat` +
session-seed bootstrap returning a schema-valid greeting turn). After this change,
`app/main.py` has exactly ONE owner — the conversation-orchestrator change (5) —
and no other change may edit it. Store-writer (13) and tracing (14) expose startup
hooks that `main.py` calls; they SHALL NOT edit `main.py` themselves.

- **Rationale:** `main.py` is a hot file (app wiring, startup hooks, route
  registry). Single ownership after the stub prevents the wiring file from becoming
  a merge-conflict magnet; other changes contribute via importable hooks.

### D13 — FY helpers are implemented here, not just typed

`app/contracts/flow.py` SHALL **implement** the financial-year helpers
(`currentFY`, `supportedFYs`, `defaultFY`, short↔long mapping) as pure date math,
not merely declare their signatures. The flow engine (2), the tax flow (9), and
the router (3) all consume them; implementing once in contracts avoids three
divergent copies of the Apr-1 rollover logic. The flow-engine-runtime change
consumes these functions and does NOT reimplement them in `app/engine`.

- **Rationale:** pure, dependency-free, multi-consumer date math is exactly what
  belongs in the shared contract layer; duplicating it risks the "never hardcode
  the three years" rule being violated inconsistently.

### D14 — Shared RAG/store contract types decouple producers from consumers

`app/contracts/rag.py` defines `RetrievedChunk` (chunk id, chunk text, source/entry
id, vector score, FTS rank, fused score), `RagAnswer` (answer text, citations →
chunk ids, refusal flag + refusal-reason enum, `retrieval_context`), and the
**canonical `retrieval_context: list[str]`** shape. `app/contracts/store.py`
defines the `TurnRecord` DTO mirroring the `0001` columns. These are frozen so
store-writer (13) and tracing (14) — which depend on contracts only and must never
import `app/rag/` — share one shape with rag-service (4) and the orchestrator (5).

- **Rationale:** `retrieval_context` is persisted by the store, put on tracing
  retriever spans, and produced by RAG; a single canonical `list[str]` shape
  prevents three definitions. `TurnRecord` is the orchestrator→store-writer queue
  contract (producer `enqueue(TurnRecord)`, consumer `insert`), so neither side
  redefines the row.

### D15 — Agentic native-tool-use loop per the Anthropic support-agent pattern

Jini SHALL use **native tool use** for every structured decision, NEVER
prompt-then-parse-JSON. `app/contracts/tools.py` defines the frozen tool set as
Anthropic tool definitions (`name`, `description`, `input_schema`) with
`strict: true`, so `tool_use.input` is API-schema-validated and no malformed-JSON
repair loop is needed:

- `route` — the router's forced classification tool; `input_schema` generated from
  `RouterResult`.
- `get_pnl_report`, `get_ledger_report` (with an `mtf` flag), `get_contract_notes`,
  `get_tax_report`, `get_cml`, `get_brokerage_slabs` — the flow fulfilment tools.
- `search_kb` — the RAG retrieval tool.
- `raise_ticket`, `get_ticket_status` — the Freshdesk tools.

Every `input_schema` is generated from the frozen Pydantic models via
`model_json_schema()` (targeting the strict-tool-use subset — `additionalProperties:
false`, `required` set, unsupported constraints stripped) and dumped to a checked-in
`app/contracts/schema/tools.schema.json` with a drift test (same pattern as
`chat_wire.schema.json`, D11). **Tool name strings are frozen**; implementations
bind at runtime via the orchestrator's registry (implementations live in the
engine / rag / ticketing changes — this change ships definitions only).

The router issues its classification as a **forced** single tool call:
`tool_choice={"type":"tool","name":"route","disable_parallel_tool_use":true}`.
Structured **non-tool** outputs (e.g. grounded RAG generation shapes) use
`output_config.format` json_schema. Prompt-then-parse-JSON is forbidden everywhere.

The orchestrator turn loop is an explicit `while` over `stop_reason`: issue the
Claude call with `tools=`; on `tool_use`, execute **all** `tool_use` blocks in the
assistant message via the registry, append the assistant content (including the
`tool_use` blocks) and return **all** `tool_result` blocks (each carrying its
matching `tool_use_id`) in **one** user message (never split across messages), then
re-call; on `pause_turn`, re-send and continue; on `end_turn`, break with the final
text; on `refusal`, map to the escalation path. The loop is **bounded at ≤3 tool
iterations per turn**, then escalates. This change deliberately chooses the
**explicit manual loop over the SDK's beta tool_runner** — no beta dependency, and
deterministic, verifiable exit conditions (per CLAUDE.md's machine-loop principle).
Structured UI events (chip / calendar / stepper selections) bypass the LLM entirely
and drive the deterministic engine directly. Fulfilment stays deterministic
**inside** the tool implementations (spec §2.2 preserved — the LLM chooses the tool;
the tool code drives the fixed flow).

- **Rationale:** the Anthropic customer-support agentic pattern — schema-validated
  tool calls, not free-text JSON — removes an entire class of parse-error handling,
  makes the router's output API-enforced, and keeps fulfilment deterministic while
  the LLM only classifies and selects tools.
- **Model pins unchanged:** the router/RAG generation still uses the owner-pinned
  `claude-sonnet-5` (toggle `claude-haiku-4-5-20251001`); the Anthropic blog's Opus
  example does NOT override the owner pin. Tool use works on the pinned models with
  adaptive thinking and no sampling params (D9).
- **Both mechanisms are used (per plan v1.1):** native `tool_use` blocks for tool
  calls (route + fulfilment + search_kb + ticket tools), and `output_config.format`
  json_schema for structured non-tool outputs. Neither path parses free-text JSON.
  The forced-`route` tool doubles as the classifier and the action surface.

## Risks / Trade-offs

- [Success schemas were captured but some are single-capture] → `models.py`
  marks unverified fields `[CONFIRM]` verbatim from `03` (MTF `Margin:1`,
  Holdings FINX-JWT provenance, Ledger-PDF email branch). Contracts encode the
  captured shape and flag the gap; flow changes must not treat `[CONFIRM]` fields
  as proven.
- [`With_Exp` changes response SHAPE on `GetGlobalPNLNew`] → the data-endpoint
  model documents both shapes (truthy → `{Trades,Expenses}` object; falsy → bare
  array) and the contract mandates always sending it truthy for a stable object
  (`03` §4.6). Parser tests cover both.
- [Contract-note + CML endpoints have live security weaknesses] → contracts bake
  in the mitigations as invariants: `file_id`/report URLs/`cmlLink` are
  server-side-only and never serialized into any wire render block or log; the
  backend gates `client_id`/`client_code` by the authenticated session (FLAG A/B,
  `03` §7; memory `finx-security-findings`).
- [Non-streaming decision could be wrong for a future long RAG answer] → recorded
  as a Phase-1 decision with an explicit "flag any objection" note (D1); revisiting
  is a wire-contract change, isolated to `wire.py`.
- [Registry contract vs implementation split across two changes] → this change
  ships only the `FlowSpec` *contract* (the shape of the module-level `FLOW`
  object); if change 2's discovery
  needs a signature tweak it is a contract edit here, so the protocol is kept
  minimal and stable.
- [Freshdesk config placed under `app/config`] → `04` §5 mandates config-driven
  ticket fields; the schema lives here but the ticket-builder (change 12) is the
  only consumer, so the shape is kept aligned with `04` §5's `config/freshdesk.yaml`.

## Migration Plan

- **Schema:** `0001_conversation_store.sql` creates `threads` and `turns` (columns
  per §3.2), plus the `schema_migrations` bookkeeping table. Forward-only; no
  destructive statements. Apply with `python -m app.store.migrations.runner`.
- **Rollback:** drop `threads`/`turns` (they are new and empty at contract-landing
  time; no data to preserve). No down-migration file is authored for a greenfield
  create — rollback is a manual drop before any writer ships (change 13).
- **Deploy:** contracts + stub only; `POST /api/chat` returns a stubbed greeting
  turn so the widget can integrate the wire shape. No live backend calls happen
  until adapters (change 1) and the orchestrator (change 5) land.

## Open Questions

- SessionId acquisition/lifetime/expiry is undocumented (`02` §9, `03` §6). The
  widget receives it via URL params; contracts assume it suffices for all
  SessionId backends but cannot verify expiry behavior — carried as a runtime risk.
- MTF `Margin:1` discriminator unverified (byte-identical on the no-MTF test
  account). `LedgerPdfRequest.Margin` is contracted with `1` marked `[CONFIRM]`.
- Holdings body `accessToken` (FINX-issued JWT, `iss:FINX`) provenance in the
  widget handoff is unresolved (`03` §4.6d) — Holdings adapter contract notes it
  `[CONFIRM]`; Holdings flow is BLOCKED regardless.
- Ledger delivery one-call-vs-two and the fallback-vs-primary role of the [DATA]
  endpoints for empty-range detection (`02` §9 7b) — resolved during
  implementation of change 2, not pinned here; both endpoints are contracted.
