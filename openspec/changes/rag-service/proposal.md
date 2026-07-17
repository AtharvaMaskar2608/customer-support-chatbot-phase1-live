# Proposal: rag-service

## Why

RAG is the answer path for every non-transactional question (`docs/technical/02_technical_spec.md` §5, §2.2) and the whole of the Phase-1 test workbook's KB-only sheet (41 cases A1–E12, §7.4). The knowledge base already exists and is locked: table `qa_chunks`, **1,102 rows, 3072-dim `text-embedding-3-large` embeddings**, single `chunk` column (`Query -> Solution -> TAT`), pgvector **sequential scan** (the 3072-dim vectors exceed pgvector's 2000-dim ANN cap, so exact scan is the correct and confirmed choice at this size — §3.1, §5.3). What does **not** exist is the retrieval + generation code, and — critically — the spec flags three things as **never specified** (§5.4): the **FTS half** of "hybrid" (no `tsvector`/`ts_rank`/fusion), the **top-K**, and the **reranker**. This change implements the hybrid retriever + grounded generator and **proposes concrete values for all three open decisions** (marked for review below).

Grounding and refusal are launch blockers: B3 (never invent numbers → ticket), C1–C3/C5–C8 (no investment advice, prompt-injection resistance, no fabrication), D4 (no-match → agent handoff) all gate release (§7.4). This change owns those behaviours.

## What Changes

- **Query embedding** — embed the user query with `text-embedding-3-large` @ **3072-dim** (locked to the stored KB dimension; `-small`/truncated vectors are forbidden against this KB, §5.1).
- **Vector search** — exact cosine (`<=>`, `vector_cosine_ops`) sequential scan over `qa_chunks.embedding`, top-`RAG_CANDIDATE_K`.
- **FTS search (the missing "hybrid" half)** — Postgres full-text over the `chunk` column: `to_tsvector('english', chunk) @@ websearch_to_tsquery('english', :q)` ranked by `ts_rank_cd`, top-`RAG_CANDIDATE_K`. **Computed inline (no stored `chunk_tsv` column, no GIN index)** in Phase 1 — mirroring the already-locked "sequential scan, no index" posture, and because `rag-service` owns no migration (see decision + ownership note).
- **RRF fusion** — combine the two ranked lists with Reciprocal Rank Fusion (`score = Σ 1/(RRF_K + rank)`), then take the top-`RAG_CONTEXT_K` fused chunks as the generation context.
- **Grounded generation** — Claude (`claude-sonnet-5` pinned via the frozen `app/llm/client.py`, Haiku toggle) answers **only** from the retrieved chunks, cites the KB entries it used, and obeys refusal rules. No prompt-then-parse-JSON: retrieval is a native tool (`search_kb`) in the agent loop, and the structured `RagAnswer` envelope (citations, refusal/escalate) is produced via **structured outputs** — `output_config: {format: {type: "json_schema", schema: <RagAnswer schema>}}` (or the SDK `messages.parse()` with the frozen `RagAnswer` Pydantic model) — not a forced tool call and not the deprecated `output_format` param.
- **Refusal + escalation** — never invents numbers (B3): a numeric gap → refuse + flag `escalate` (→ Freshdesk ticket); never gives investment advice (C-series); resists prompt injection; on no useful match (D4) → refuse + flag handoff. Refusals are grounded, not apologetic guesses.
- **Tracing/eval plumbing** — returns `retrieval_context` (the fused chunks + per-retriever scores) on every response so the conversation store, tracing spans, and DeepEval `retrieval_context` all get the real retrieved set (§6, §7.2 `LLMTestCase(..., retrieval_context)`).

### Proposed decisions (§5.4 — for review)

| Decision | Proposed value | Rationale |
|---|---|---|
| **Candidate depth per retriever** (`RAG_CANDIDATE_K`) | **25** | Deep enough that RRF has real signal from both lists; trivial cost at 1,102 rows. |
| **RRF constant** (`RRF_K`) | **60** | The canonical Cormack et al. value; robust default, avoids over-weighting rank-1. |
| **Final context size** (`RAG_CONTEXT_K`) | **5** | Matches the guide's tutorial `k`; keeps precision high. Chunks are tiny (max 653, mean 58.68 tokens, §5.2) so raising it later is cheap — kept configurable. |
| **Reranker** | **Explicit skip (`reranker: none`)** | At 1,102 rows the vector scan is already 100%-recall/exact; a hosted cross-encoder (e.g. Cohere Rerank) adds an external dependency + latency for no measurable gain at this scale. RRF is the ranking mechanism. A `reranker` config slot is retained so one can be dropped in later and scored by `ContextualPrecisionMetric` (§7.2). |
| **FTS storage** | **Inline `to_tsvector`, no stored column/index** | Avoids a `qa_chunks` migration `rag-service` does not own; O(n) over 1,102 rows matches the locked sequential-scan posture. |
| **Distance metric** | **Cosine** (locked, §5.3) | — |

## Capabilities

### New Capabilities

- `rag-service`: hybrid retrieval (vector + FTS + RRF) over the existing `qa_chunks` KB, plus grounded, citation-bearing answer generation with refusal/escalation and `retrieval_context` output for tracing and eval.

### Modified Capabilities

None — reuses the existing `qa_chunks` KB unchanged and consumes frozen `contracts-foundation` contracts.

## Impact

- **New code**: `app/rag/**` (embedding, retriever, fusion, generator, service, RAG-specific prompts); tests under `tests/rag/**`.
- **Data**: reads `qa_chunks` **read-only**; adds no table, column, or index (see FTS decision). The KB is not re-embedded.
- **Runtime**: one OpenAI embedding call + one Claude call per query, both server-side.
- **Downstream**: the orchestrator (change 5) routes RAG-intent turns here; the conversation store and tracing consume the emitted `retrieval_context`.

## Files touched

Exclusive ownership (ownership map row 4), nothing outside it:

- `app/rag/embeddings.py` — query embedding (`text-embedding-3-large` @ 3072).
- `app/rag/retriever.py` — vector search, FTS search, RRF fusion.
- `app/rag/generator.py` — grounded generation + refusal/escalation.
- `app/rag/service.py` — public entry (`respond`), wiring retrieve → answer → `RagAnswer`.
- `app/rag/models.py` — `RetrievedChunk`, `RagAnswer`, `RetrievalContext` (see contracts note).
- `app/rag/config.py` — `RAG_CANDIDATE_K`, `RRF_K`, `RAG_CONTEXT_K`, `reranker` defaults.
- `app/rag/prompts/**` — grounded-answer system prompt + refusal rules (RAG prompts live here, not under `app/llm/prompts/` which `llm-router` owns).
- `tests/rag/**` — retrieval fixtures, seeded-DB tests, fake-retriever generation tests.

**Untouched**: lockfiles, **all migrations** (no `qa_chunks` DDL — FTS is inline), and root config are **not** modified by this change. `app/llm/client.py` and `contracts-foundation` types are imported read-only.

## Contracts & API structure

Public surface (`app/rag/`). `RetrievedChunk`/`RagAnswer`/`RetrievalContext` are **frozen contracts-foundation types** (`app/contracts/rag.py`, design D14 — promoted during the 2026-07-17 Gate-1 reconciliation); `app/rag/models.py` re-exports them.

- `respond(query: str, ctx: ConversationContext) -> RagAnswer` — public entry: retrieve → answer, attaches `retrieval_context`, carries the sticky-language decision through to generation.
- `retrieve(query: str, k: int = RAG_CONTEXT_K) -> list[RetrievedChunk]` — embeds the query, runs vector + FTS search (each top-`RAG_CANDIDATE_K`), RRF-fuses, returns the top-`k` fused chunks.
- `answer(query: str, context: list[RetrievedChunk]) -> RagAnswer` — grounded Claude generation over `context` only; enforces refusal/escalation; produces citations.
- `RetrievedChunk` — `{ chunk_id: int (qa_chunks.id), chunk: str, vector_score: float, fts_score: float, rrf_score: float, rank: int }`.
- `RagAnswer` — `{ text: str, citations: list[int] (chunk_ids), retrieval_context: list[RetrievedChunk], refused: bool, escalate: bool, escalate_reason: str | None, language, model: str, usage, latency_ms }`.
- **Error behavior**: no data / empty retrieval → `refused=True, escalate=True` (D4 handoff), never a fabricated answer. Numeric gap (B3) → `refused=True, escalate=True` with `escalate_reason="numeric_gap"`. Embedding/LLM/DB failures raise a typed `RagError` for the orchestrator to map to the shared error taxonomy (E-TIMEOUT/E-UNKNOWN, §8.4) — no user-facing copy is produced here.
- **DB access**: parameterized SQL against `qa_chunks` via the shared async DB session (see Dependencies). No FinX/Freshdesk endpoints — no `03_finx_api_reference.md` entry applies. Query text and `chunk` bodies are masked per the tracing `mask` contract before they reach spans/store.
- **Native tool exposure** (Gate-1 agentic pattern): retrieval is exposed to the agent loop as the frozen native tool **`search_kb`** (per `contracts-foundation`'s tool registry, `app/contracts/tools.py`) — the orchestrator's tool-use loop calls `search_kb(query)`, whose body runs `retrieve` and returns the fused chunks as `tool_result` content; `rag-service` implements the tool body. The `respond`/`retrieve`/`answer` signatures above are unchanged. Grounded generation returns prose, but the **structured** `RagAnswer` envelope (`citations`, `refused`/`escalate`) is produced via **structured outputs** — `output_config: {format: {type: "json_schema", schema: <RagAnswer schema>}}` (or the SDK `messages.parse()` with the frozen `RagAnswer` Pydantic model) — not a forced tool call, never hand-parsed JSON, and not the deprecated `output_format` param.

## Dependencies & contracts consumed

**Consumed from `contracts-foundation` (must land in main first):**
- `llm-client`: `app/llm/client.py` (pinned `claude-sonnet-5` + Haiku toggle) for generation.
- tool registry + output schemas: the frozen `search_kb` tool schema (native tool-use loop; `strict: true`) and the frozen `RagAnswer` json_schema consumed via structured outputs (`output_config.format` / `messages.parse()`) — both in `app/contracts/tools.py`.
- `router-contract` / `chat-wire-api`: `ConversationContext` (input to `respond`) and the language signal.
- `tracing-conventions`: the `mask` signature and retriever/llm span taxonomy (§6).
- Shared **async DB session/engine** for reading `qa_chunks`.

**RESOLVED — folded into `contracts-foundation` (2026-07-17 Gate-1 reconciliation).** The four fan-out blockers this proposal originally surfaced are all closed in the updated contracts-foundation proposal/design/specs:
- `openai`, the async Postgres driver (`psycopg[binary]`), and the `pgvector` adapter are declared in the locked deps (design D8).
- The shared async DB engine/session factory is contracts-owned at `app/config/db.py` (design D7); `qa_chunks` reads go through it.
- `RetrievedChunk` / `RagAnswer` / the canonical `retrieval_context` shape are frozen in `app/contracts/rag.py` (design D14); store-writer and tracing consume them without importing `app/rag/`. `app/rag/models.py` re-exports the frozen types.
- RAG tunables (`rag_candidate_k=25`, `rrf_k=60`, `rag_context_k=5`, `reranker="none"`) are in the frozen remote-config schema; `app/rag/config.py` mirrors those keys.

**Parallelism**: depends only on `contracts-foundation` (row 4, "depends on 0"). No file overlap with `llm-router`, `finx-http-adapters`, or `flow-engine-runtime` — runs fully in parallel once contracts land.

## Done condition & test command

**Done when**: hybrid retrieval returns the expected fused ranking against a seeded test DB, and generation produces grounded, citation-bearing answers that **refuse-and-escalate** on the B3 (numeric-gap) and D4 (no-match) cases and refuse investment advice / resist prompt injection (C-series) — all without a live LLM in CI.

**Test-DB strategy (chosen): ephemeral pgvector via Docker.** Retrieval tests run against a throwaway `pgvector/pgvector:pg16` container seeded from a committed JSONL fixture (`tests/rag/fixtures/qa_chunks_seed.jsonl`, ~30 representative rows with real 3072-dim vectors captured from prod + hand-picked FTS/vector-divergent cases), so the actual FTS + `<=>` + RRF SQL is exercised against real pgvector semantics. Generation/refusal tests use a `FakeRetriever` returning canned `RetrievedChunk` lists and a `FakeLLMClient` replaying recorded Claude completions — no DB, no network. (A `pgvector-lite`/pure-Python fake was rejected: it would not exercise the SQL that is the substance of this change.)

**Test command**: `pytest tests/rag/` (green; retrieval tests skip cleanly if Docker is unavailable and run in CI where it is; generation/refusal tests need neither DB nor network).
