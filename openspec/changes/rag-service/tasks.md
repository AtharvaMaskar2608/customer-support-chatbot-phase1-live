# Tasks: rag-service

Implements hybrid retrieval (vector + FTS + RRF) over the frozen `qa_chunks`
KB plus grounded, citation-bearing generation with refusal/escalation, all on
the frozen `contracts-foundation` surface. Public API: `respond` / `retrieve` /
`answer` (+ the `search_kb` tool body). Types re-export the frozen
`app/contracts/rag.py` shapes; only `RagError` is new.

- [ ] 1. **config + models.** `app/rag/config.py` — `RagConfig` mirroring the
  frozen `RagTunables` (`rag_candidate_k=25`, `rrf_k=60`, `rag_context_k=5`,
  `reranker="none"`) with a `from_tunables` adapter. `app/rag/models.py` —
  re-export frozen `RetrievedChunk` / `RagAnswer` / `RetrievalContext` /
  `RefusalReason`; define new typed `RagError(stage=...)` (embedding|db|llm).

- [ ] 2. **query embeddings.** `app/rag/embeddings.py` — `QueryEmbedder` using
  `text-embedding-3-large` @ **3072 dims** (locked to the stored KB dimension;
  `-small`/truncated forbidden). Injectable OpenAI client (lazy; buildable with
  no API key). Failures → `RagError(stage="embedding")`.

- [ ] 3. **hybrid retriever.** `app/rag/retriever.py` — over the shared async
  `Database`:
  - vector search: exact cosine `embedding <=> :qvec` (`vector_cosine_ops`)
    sequential scan, `vector_score = 1 - distance`, top `candidate_k`; query
    vector passed as `pgvector.Vector`.
  - FTS search: inline `to_tsvector('english', chunk) @@
    websearch_to_tsquery('english', :q)` ranked by `ts_rank_cd`, top
    `candidate_k` (semantically identical to the DB's stored generated `fts`
    column — see loop.md note).
  - RRF fusion: `score = Σ 1/(rrf_k + rank)` over the two rank lists; return
    top `context_k` `RetrievedChunk` (`chunk_id=str(id)`,
    `source_id="{source_sheet}:{source_row}"`, `text=chunk`).
  - opens a masked `retriever` tracing span; DB failure →
    `RagError(stage="db")`.

- [ ] 4. **grounded generator + prompts.** `app/rag/generator.py` +
  `app/rag/prompts/**` — grounded Claude generation over the retrieved context
  **only**, via the frozen `LLMClient` with **structured outputs**
  (`output_config.format` json_schema; never prompt-then-parse free-text JSON).
  Enforce refusal/escalation mapped onto the frozen `RagAnswer`
  (`refused` + `RefusalReason`): D4 no-match → `no_relevant_context`; C-series
  investment advice → `investment_advice`; prompt-injection / out-of-scope →
  `out_of_scope`; B3 numeric-gap → `low_confidence`. Citations validated to
  retrieved `chunk_id`s. LLM failure → `RagError(stage="llm")`.

- [ ] 5. **service.** `app/rag/service.py` — `RagService` (DI: db, embedder,
  llm, config) with `respond` / `retrieve` / `answer` / `search_kb`; module-level
  `respond` / `retrieve` / `answer` delegating to a lazily-built default service.
  `respond` attaches the real `retrieval_context: list[str]` and threads the
  sticky-language decision (`ConversationContext.detected_language`) into
  generation. `search_kb(query)` = the tool body running `retrieve`.

- [ ] 6. **tests (from the proposal).** `tests/rag/**`:
  - retrieval: ephemeral `pgvector/pgvector:pg16` container seeded from the
    committed `tests/rag/fixtures/qa_chunks_seed.jsonl` (31 real 3072-dim rows);
    exercises real FTS + `<=>` + RRF; **skips cleanly** when Docker/image is
    unavailable.
  - generation/refusal: `FakeRetriever` + `FakeLLMClient` (no DB, no network) —
    B3 numeric-gap, C-series investment-advice + prompt-injection, D4 no-match,
    grounded citation happy path.
  - config + models + embeddings (fake client) unit tests.

- [ ] 7. **verify + ship.** `pytest tests/rag/` green; fresh 3-lens verifier
  panel; fix findings; rebase onto `origin/main`; full `uv run pytest` green;
  push + open PR.
