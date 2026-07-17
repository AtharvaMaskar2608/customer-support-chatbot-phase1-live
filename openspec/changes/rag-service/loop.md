# loop.md — rag-service worktree

Branch: `rag-service` (worktree `/home/choice/projects/customer-support/rag-service`).
Base: `main @ cfb22a1` (frozen contracts landed). Owner directive: fast single
verifier round, PR target ~35 min.

## Status

- Current task: **Task 1 — config + models** (about to start after committing scaffold).
- Tasks completed: scaffold (tasks.md + loop.md).
- Verifier rounds run: 0.
- Escalations: none yet (two proposal-vs-frozen discrepancies recorded below; both
  resolved in favour of the frozen contract without deviating from spec intent —
  flagged for the team lead in the final report, not blocking).

## Environment facts (verified this session)

- `uv sync --all-extras` OK. numpy is **NOT** installed → query vectors passed as
  `pgvector.Vector`, never numpy arrays.
- Docker running; `pgvector/pgvector:pg16` pulled locally → retrieval container
  tests run here (skip cleanly elsewhere).
- Live DB tunnel `localhost:5433` reachable (SELECT-only used for schema + fixture
  capture; **no DDL/DML** issued).

## `qa_chunks` actual schema (live prod, SELECT `\d`)

`id bigint PK`, `topic text`, `section text`, `question text`, `answer text`,
`answer_source text`, `tat text`, `source_sheet text`, `source_row int`,
`chunk text NOT NULL`, `embedding vector(3072)`,
`fts tsvector GENERATED ALWAYS AS to_tsvector('english', COALESCE(chunk,'')) STORED`.
Indexes: `qa_chunks_pkey` (id), `qa_chunks_fts_gin` GIN(fts). 1,102 rows, all with
embeddings, 18 source sheets.

## Contract mapping (frozen `app/contracts/rag.py` is authoritative)

`RetrievedChunk`: `chunk_id:str, text:str, source_id:str, vector_score:float,
fts_rank:float, fused_score:float` (frozen). Mapping:
- `chunk_id = str(qa_chunks.id)`
- `text = qa_chunks.chunk`
- `source_id = f"{source_sheet}:{source_row}"` (KB-entry provenance)
- `vector_score = 1 - cosine_distance`, `fts_rank = ts_rank_cd`, `fused_score = RRF`

`RagAnswer` (frozen): `answer:str, citations:list[str], refused:bool,
refusal_reason:RefusalReason|None, retrieval_context:list[str]`. `RefusalReason`
enum = {no_relevant_context, out_of_scope, low_confidence, investment_advice}.

## DISCREPANCY 1 — proposal RagAnswer shape ≠ frozen (resolved: use frozen)

proposal.md §Contracts describes `RagAnswer` with `text/escalate/escalate_reason/
language/model/usage/latency_ms` and `retrieval_context: list[RetrievedChunk]`.
The frozen contract (promoted at the 2026-07-17 reconciliation) has none of those;
`retrieval_context` is `list[str]`. The proposal ITSELF instructs "app/rag/models.py
re-exports them [the frozen types]", so the frozen shape wins. Behavioural
escalation is mapped onto `refused + refusal_reason`:
- D4 no-match → `refused, no_relevant_context` (orchestrator → agent handoff)
- C-series investment advice → `refused, investment_advice`
- prompt-injection / out-of-scope → `refused, out_of_scope`
- **B3 numeric-gap → `refused, low_confidence`** (no `escalate`/`numeric_gap`
  field exists; orchestrator escalates low_confidence → ticket). This is the one
  lossy mapping — flag to team lead.

## DISCREPANCY 2 — stored `fts` column exists (proposal said it doesn't)

proposal.md line 13/§decisions claims Phase-1 has "no stored chunk_tsv column, no
GIN index" and mandates inline `to_tsvector`. Reality: prod already HAS the
generated `fts` tsvector + `qa_chunks_fts_gin`. Implementing the spec as written
(inline `to_tsvector('english', chunk)`) is **semantically identical** (chunk is
NOT NULL, same regconfig) and still correct, just index-unused → matches the
locked sequential-scan posture. No deviation; flagged as a trivial future
speed-up (switch to `WHERE fts @@ …`).

## SQL validated against real pgvector (read-only prod probe)

Vector: `ORDER BY embedding <=> :qvec LIMIT k`, self-match ranked 1 @ score 1.0.
FTS: inline `to_tsvector` + `websearch_to_tsquery` + `ts_rank_cd` returns keyword
matches. `Vector(list)` param adaptation confirmed. See scratchpad/probe_sql.py.

## Open questions

- None blocking. Both discrepancies resolved toward the frozen contract per the
  proposal's own re-export instruction.
