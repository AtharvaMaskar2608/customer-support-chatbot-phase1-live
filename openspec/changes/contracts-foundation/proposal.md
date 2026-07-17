# Proposal: contracts-foundation

## Why

Phase-1 build fan-out is blocked: per `CLAUDE.md`, shared types/interfaces/API schemas must land in main before any parallel task starts, and `docs/technical/02_technical_spec.md` §9 (build-readiness verdict READY-WITH-CAVEATS, 2026-07-16) names the contracts-first change as the explicit next build step. Today none of these contracts exist as code — no chat endpoint schema, no Intent enum, no `FinXClient` interface — so every downstream task (11 report flows, RAG service, widget shell, conversation store, tracing) would invent its own shapes and collide in main.

## What Changes

Everything here is **contracts + their thin enforcement code** — typed models, parsers with fixture tests, config schemas, one DB migration, and a chat-endpoint stub. No flow logic, no router prompt, no RAG retrieval, no widget UI.

- **Widget ↔ backend wire contract** — chat endpoint request/response schema (session context from URL params: `userId`, `sessionId`, `accessToken`, `isDarkTheme`, `platform`, `page`) and the render-block wire types: bot/user bubble, quick-reply chip row, stepper card, in-chat calendar, file card, note-list card, data card, error bubble, ticket confirmation, generating indicator. Includes the Phase-1 non-streaming decision, the session-seed config delivery (the widget's only network surface is `POST /api/chat`), and a checked-in generated JSON Schema of the wire union for widget TS codegen. Note-list rows carry an opaque session-scoped `downloadToken`, never the FinX `file_id`.
- **Router I/O contract** — the complete `Intent` enum (all 11 report intents + RAG + ticket + ticket-status + call-support + smalltalk/fallback), `ExtractedParams` (FY, date range, segment, format, delivery), `ConversationContext` (bootstrap fields + history refs + turn_number + follow_up_count + sticky-language state), and `RouterResult` (intent, extracted_params, needs_confirmation, follow_up_question, detected_language, escalate, education_line). Defined in full up front; flow tasks are forbidden from editing it.
- **Shared cross-cutting contract types** — `app/contracts/rag.py` (`RetrievedChunk`, `RagAnswer`, the canonical `retrieval_context: list[str]` shape) and `app/contracts/store.py` (`TurnRecord` DTO mirroring the `0001` columns). Consumed by rag-service, orchestrator, store-writer, and tracing, which depend on contracts only and never import `app/rag/`.
- **Native tool-use tool registry** — `app/contracts/tools.py`: frozen Anthropic tool definitions (`name`, `description`, `input_schema`, `strict: true`) for `route`, `get_pnl_report`, `get_ledger_report` (mtf flag), `get_contract_notes`, `get_tax_report`, `get_cml`, `get_brokerage_slabs`, `search_kb`, `raise_ticket`, `get_ticket_status` — every `input_schema` generated from the frozen Pydantic models with a checked-in `app/contracts/schema/tools.schema.json` + drift test. Tool names are frozen; implementations bind at runtime via the orchestrator registry. Jini uses native tool use everywhere (the Anthropic support-agent pattern) — never prompt-then-parse-JSON.
- **`FinXClient` interface** — per-backend adapter set (NOT one wrapper) for the five FinX hosts/auth schemes: `.NET /api/middleware` (SessionId header+body), Go `/middleware-go` on `finx.` and `api.` hosts, `/mis` (SSO JWT), `mf.` profile (SSO JWT), `finxomne. /COTI` (SessionId + ssotoken + FINX-JWT). Three envelope parsers (`{Status,Response,Reason}`, `{StatusCode,Message,DevMessage,Body}`, MIS/JWT), typed request/response models per captured endpoint, and capture fixtures from the 2026-07-16 live tests as parser test data.
- **Flow/Step state-machine contract** — `FlowState`, `Step`, transition types, per-flow date-window config (floors/caps/max-range differ by design), FY helpers (`currentFY`, rolling 3-FY window — never hardcoded), byte-validation + retry + 15-min cache semantics as typed config.
- **Conversation-store migration** — single-owner PostgreSQL DDL in `app/store/migrations/0001_*` (contracts-foundation owns `0001`; conversation-store-writer owns `0002+` in the same directory): threads/turns with intent, tool calls + args + results, retrieval context, latency/token usage, model version, turn number (serves the 10-message cap and future fine-tuning). The `TurnRecord` DTO that mirrors these columns is the producer/consumer contract between orchestrator (`enqueue`) and store-writer (`insert`).
- **Shared async DB access** — `app/config/db.py` (async engine + session factory) is the single access point for both the `qa_chunks` read path (RAG) and the conversation-store write path.
- **Remote-config schema** — `whats_new`, limits (page size 10, note threshold 50, message cap 10, follow-up cap 2), chip sets per entry surface, greeting pool, product list, per-flow calendar bounds, and RAG tunables (`rag_candidate_k` 25, `rrf_k` 60, `rag_context_k` 5, `reranker` "none"). The client-relevant slice is delivered in the first `/api/chat` response, not fetched separately.
- **Tracing conventions** — span taxonomy (agent/retriever/llm/tool), `trace_manager.configure()` setup contract, PII `mask` function signature.
- **Error taxonomy as shared config** — E-NODATA / E-YEAR / E-TIMEOUT / E-FETCH / E-UNKNOWN with verbatim copy and recovery-chip sets from spec §8.4.
- **LLM client wrapper** — pinned model IDs (`claude-sonnet-5`, toggle `claude-haiku-4-5-20251001`), backend-configurable toggle, no business logic.

## Capabilities

### New Capabilities

- `chat-wire-api`: the widget↔backend HTTP contract — chat endpoint schema, session bootstrap, and every render-block wire type the widget can display.
- `router-contract`: Intent enum, ExtractedParams, RouterResult — the router's complete input/output surface.
- `finx-client`: per-backend FinX adapter interfaces, the three response-envelope parsers, typed endpoint models, and capture-fixture test data.
- `flow-engine-contract`: flow/step state-machine types, per-flow date-window and guardrail config, FY/date helpers, byte-validation and cache semantics.
- `conversation-store`: the conversation persistence schema and its migration.
- `remote-config`: the runtime-tunable config schema (limits, chips, greeting pool, whats_new, products).
- `tracing-conventions`: span taxonomy, tracing setup, and PII masking contract.
- `error-taxonomy`: the shared conversational error codes, copy, and recovery chips.
- `llm-client`: the pinned-model Claude client wrapper contract.

### Modified Capabilities

None — `openspec/specs/` is empty; this is the first change.

## Impact

- **Files touched** (this change owns exclusively): `pyproject.toml` + lockfile, `.env.example`, `app/main.py` (stub), `app/contracts/**` (incl. `wire.py`, `router.py`, `flow.py`, `errors.py`, `tracing.py`, `rag.py`, `store.py`, `tools.py`, and the generated `app/contracts/schema/chat_wire.schema.json` + `app/contracts/schema/tools.schema.json`), `app/finx/{interfaces,envelopes,models}.py`, `app/llm/client.py`, `app/config/**` (incl. `schema.py`, `defaults.py`, `db.py`), `app/store/{schema.py,migrations/0001_*,migrations/runner.py}`, `tests/contracts/**`, `tests/finx/**`, `tests/fixtures/finx/**`. Migrations live in `app/store/migrations/` (single directory; `0001` here, `0002+` for the writer change). No Freshdesk field-mapping file is created here — it stays ticketing-owned at `app/ticketing/freshdesk.yaml`.
- **APIs**: defines (does not yet fully implement) `POST /api/chat` and the session-seed bootstrap; all FinX/Freshdesk calls remain server-side only.
- **Dependencies** (declared up front; no other change may edit `pyproject.toml`/lockfile): `fastapi`, `uvicorn[standard]`, `pydantic` (v2, locked), `httpx`, `anthropic`, `openai` (query embeddings, `text-embedding-3-large`@3072), `deepeval`, `psycopg[binary]` + `pgvector` (async engine + vector adapter), `pytest`, `pytest-asyncio`, and `respx` (the single repo-wide httpx mock, for adapter/ticketing/rag fixture tests). Migrations are plain forward-only SQL (no Alembic). `.env.example` carries `FRESHDESK_API_KEY`, `FRESHDESK_API_ROOT`, plus the DB/OpenAI/Anthropic keys. `deepeval` + `pytest` + `respx` sit in a dev/eval extras group; the DeepEval judge model is `claude-opus-4-8` via the existing `anthropic` SDK (no new dep).
- **Downstream**: unblocks parallel fan-out — flow tasks, RAG service, widget shell, tracing, and eval tasks all import these contracts and are forbidden from editing the Intent enum, `FinXClient` interface, remote-config schema, and `app/main.py` (sole owner after this stub is the conversation-orchestrator change) (spec §9 merge-conflict watch).
- **Explicitly out of scope**: flows without captured endpoints stay BLOCKED per owner decision (Brokerage data rendering is captured; Holding file delivery, Global-Detail download are BLOCKED — their intents exist as enum values only). The Freshdesk field mapping (`04_freshdesk_api_reference.md` §5) is ticketing-owned config (`app/ticketing/freshdesk.yaml`), not part of the frozen remote-config; only the raise-ticket tool contract rides in `router-contract` and the recovery chips in `error-taxonomy`.
