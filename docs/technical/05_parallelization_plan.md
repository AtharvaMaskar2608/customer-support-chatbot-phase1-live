# Jini Phase 1 — Parallelization Plan

> **Status: v1.1 — GATE 1 APPROVED (2026-07-17).** The owner approved the 17
> proposals + this plan as one batch, kept the three-way Tax intent split
> (`report_tax` / `report_capital_gain` / `report_tax_pnl` → one tax
> FlowDefinition), and blessed the proposed decision values (RAG k=25 / RRF 60 /
> context 5 / reranker none; eval thresholds 0.7–0.9; judge `claude-opus-4-8`;
> Ledger PDF cap today+7 [CONFIRM pending one capture]).
>
> **Gate-1 amendment (owner): the Anthropic agentic tool-use pattern is
> mandatory.** All LLM interactions use native tool use — tools declared as
> `{name, description, input_schema}` with `strict: true` (API-validated
> `tool_use.input`), the router as a forced tool call
> (`tool_choice={"type":"tool","name":"route","disable_parallel_tool_use":true}`),
> structured non-tool outputs via `output_config.format` json_schema, and the
> orchestrator running an explicit `while stop_reason == "tool_use"` loop
> (execute all tool_use blocks → ALL tool_results in ONE user message →
> re-call; pause_turn re-sent; refusal → escalation; ≤3 iterations/turn).
> Prompt-then-parse-JSON is forbidden everywhere. The frozen tool registry
> lives in `app/contracts/tools.py` (+ generated `tools.schema.json` with a
> drift test); tool implementations bind at runtime (engine/rag/ticketing).
> Fulfilment stays deterministic INSIDE tool implementations — spec §2.2
> preserved. Structured UI events (chip/calendar/stepper) bypass the LLM.
>
> Derived from the 17 OpenSpec change proposals in `openspec/changes/` after
> the cross-proposal merge-conflict review mandated by `CLAUDE.md`. The
> file-ownership map is authoritative; a change may only touch the files its
> own proposal lists.

## 1. The 17 changes

| # | Change | One-line scope | Test command |
|---|---|---|---|
| 0 | `contracts-foundation` | All frozen types/interfaces/schemas + parsers + fixtures + migration 0001 + chat stub + pyproject (all deps) | `pytest tests/contracts tests/finx` |
| 1 | `finx-http-adapters` | The 5 FinX host/auth transport adapters + byte-fetch/magic-byte helper | `pytest tests/finx_adapters` |
| 2 | `flow-engine-runtime` | Deterministic state-machine executor + discovery registry + cache/retry/error mapping | `pytest tests/engine` |
| 3 | `llm-router` | Intent classification + param extraction (record/replay, no live LLM in CI) | `pytest tests/llm_router` |
| 4 | `rag-service` | Hybrid FTS+vector+RRF retrieval over `qa_chunks` + grounded generation/refusal | `pytest tests/rag` |
| 5 | `conversation-orchestrator` | `POST /api/chat` pipeline, session, caps, greeting; sole owner of `app/main.py` post-stub | `pytest tests/orchestrator` |
| 6 | `flow-pnl` | P&L via `GetGlobalPNLPDF` (stepper 2a) | `pytest tests/flows/test_pnl.py` |
| 7 | `flow-ledger-mtf` | Ledger/MTF via `GetLedgerDetailsPDF` (`Margin` [CONFIRM]) | `pytest tests/flows/test_ledger.py` |
| 8 | `flow-contract-notes` | Note list + per-note download (opaque `downloadToken`, FLAG-A defense) | `pytest tests/flows/test_contract_notes.py` |
| 9 | `flow-tax-report` | Tax/CG via `GetTaxReportPDF` (FY window, AY→FY confirm) | `pytest tests/flows/test_tax.py` |
| 10 | `flow-cml` | CML via `/mis/reports/generate` (JWT backend, FLAG-B defense) | `pytest tests/flows/test_cml.py` |
| 11 | `flow-brokerage` | Brokerage data card (dynamic rows, verbatim desc) | `pytest tests/flows/test_brokerage.py` |
| 12 | `ticketing-freshdesk` | Raise-ticket + status tools, dedupe, transcript payloads | `pytest tests/ticketing` |
| 13 | `conversation-store-writer` | Async turn persistence (log+drop policy); migrations 0002+ owner | `pytest tests/store` |
| 14 | `tracing-observability` | DeepEval spans, PII mask, thread stitching, prod guard | `pytest tests/tracing` |
| 15 | `widget-shell` | React widget: all render blocks, both entries, theming; mock-server driven | `npm --prefix widget test` |
| 16 | `eval-harness` | ≥20 goldens, simulator plumbing, thresholds, blocker CI gate | `deepeval test run evals/` |

Blocked (not proposed, owner decision): Holding-statement flow (FINX-JWT provenance +
no captured file leg), Global-Detail file delivery, get-profile personalization (Phase 2).

## 2. Wave structure

```
WAVE 0 (serial, gates everything)
  └── 0 contracts-foundation  → lands in main FIRST

WAVE 1 (all parallel, start the moment 0 lands in main)
  ├── 1 finx-http-adapters          (contracts only)
  ├── 2 flow-engine-runtime         (contracts + adapter byte-fetch signature)
  ├── 3 llm-router                  (contracts only)
  ├── 4 rag-service                 (contracts only)
  ├── 5 conversation-orchestrator   (contracts + in-memory fakes of 2/3/4/12)
  ├── 6–11 six flow changes         (contracts + fixtures; engine/adapters mocked)
  ├── 12 ticketing-freshdesk        (contracts only)
  ├── 13 conversation-store-writer  (contracts only)
  ├── 14 tracing-observability      (contracts only)
  ├── 15 widget-shell               (wire contract + generated JSON schema; mock server)
  └── 16 eval-harness               (contracts only; authoring + unit level)

WAVE 2 (integration, after the relevant Wave-1 changes merge)
  ├── orchestrator swaps fakes → real router/engine/rag/ticketing
  ├── flows integration-verified against real engine + adapters
  ├── widget pointed at the real POST /api/chat
  └── eval-harness full ConversationSimulator runs vs the assembled app
```

Every Wave-1 task codes against the **frozen contracts + fixtures**, so no Wave-1
task waits on another. Merge order within Wave 1 is free (land as ready); the only
ordering constraints are the integration steps in Wave 2.

## 3. Hard rules (merge-conflict prevention)

1. **Frozen on land of change 0**: `app/contracts/**`, `app/finx/interfaces.py`,
   `app/finx/envelopes.py`, `app/finx/models.py`, `app/llm/client.py`,
   `app/config/**` (incl. remote-config schema), the Intent enum. No other change
   edits these, ever. Additions require a new OpenSpec change against
   `contracts-foundation`'s specs.
2. **`app/main.py`**: contracts-foundation writes the stub; conversation-orchestrator
   is sole owner thereafter; store-writer/tracing only expose `start()/stop()`
   hooks that main.py calls.
3. **Migrations**: one chain in `app/store/migrations/` — `0001` owned by
   contracts-foundation, `0002+` solely by conversation-store-writer. Nobody else
   creates migrations (ticketing's durable idempotency table, RAG's optional FTS
   index both route through change 13 if ever needed).
4. **`pyproject.toml` + lockfile**: contracts-foundation only; it declares ALL
   backend deps up front (fastapi, pydantic v2, httpx, anthropic, openai,
   pgvector adapter, async driver, alembic/SQL, deepeval, pytest + the single
   repo-wide httpx mock lib). Frontend deps live only in `widget/package.json`
   (widget-shell exclusive).
5. **`app/flows/__init__.py`**: flow-engine-runtime only; importlib discovery.
   Flow modules self-register via a module-level `FLOW` definition — no
   registration imports, no per-flow edits to any shared file.
6. **Byte-fetch split** (blessed): fetch + size-floor/magic-byte check lives once
   in `app/finx/adapters/` (`fetch_report_bytes` → `FinXFetchError`); the engine
   owns retry-once + E-FETCH/E-TIMEOUT mapping. No duplication.
7. **Security invariants** (every flow + wire type): FinX URLs/`file_id`s never
   reach the client or logs; note-list rows carry an opaque session-scoped
   `downloadToken`; `client_id` always bound to the authenticated session
   (contract-note endpoints have NO auth — 03 §7 FLAG A); CML/report signed URLs
   are not a boundary (FLAG B) — always server-side fetch.

## 4. Conflict register (surfaced during proposal review → resolution)

| # | Conflict | Resolution |
|---|---|---|
| 1 | `openai`, async driver, pgvector adapter, httpx, mock lib, deepeval missing from declared deps | Added to contracts-foundation pyproject (items 1, 12) |
| 2 | `RetrievedChunk`/`RagAnswer`/`retrieval_context` defined in `app/rag/` but consumed by store-writer + tracing | Promoted to frozen `app/contracts/rag.py` (item 2) |
| 3 | `ConversationContext` not enumerated anywhere | Frozen contracts type (item 3) |
| 4 | `RouterResult` fields underspecified | Frozen fields incl. `needs_confirmation`, `detected_language`, `escalate` (item 4) |
| 5 | RAG tunables not in remote-config | Added `rag_candidate_k=25`, `rrf_k=60`, `rag_context_k=5`, `reranker="none"` (item 5) |
| 6 | No shared async DB engine/session factory | contracts-foundation owns `app/config/db.py` (item 6) |
| 7 | Widget TS types vs Pydantic drift | contracts-foundation emits checked-in `chat_wire.schema.json` + drift test; widget generates TS from it (item 7) |
| 8 | Remote-config delivery to widget | Folded into first `/api/chat` seed response; widget has ONE network surface (item 8) |
| 9 | Migrations dir mismatch (`app/db/` vs `app/store/`) | `app/store/migrations/` everywhere (item 9) |
| 10 | `TurnRecord` DTO had no owner (orchestrator produces, store-writer consumes) | Frozen in contracts conversation-store capability (item 10) |
| 11 | `.env.example` Freshdesk keys unowned | contracts-foundation adds them (item 11) |
| 12 | Freshdesk field mapping location | Ticketing-owned `app/ticketing/freshdesk.yaml`, NOT frozen config |
| 13 | Byte-validation ownership overlap (map row 2 vs adapters) | Blessed split — rule 6 above |
| 14 | `app/main.py` dual-listing | Stub→orchestrator handoff — rule 2 above |

## 5. Open [CONFIRM]/[GAP] register (non-blocking; verify during API-verification phase)

- `Margin:1` = MTF discriminator on `GetLedgerDetailsPDF` — needs ONE capture from an MTF-holding account.
- `RequestFor:1` email branch on Ledger PDF — untested.
- `GROUP1` case-sensitivity — sent uppercase as captured.
- Dual-note day (Grp1+MCX) shape — segment badge path is a design assumption.
- Contract-note "today's note" publish time (EC-3) — yesterday-fallback copy until known.
- Tax EC-9 (client with no registered email) — hide email chip if it can occur.
- CML PDF password status [ASSUMPTION: none]; `/mis/reports/generate` generic-generator shape beyond `reportType:"cml"`.
- Holdings FINX-JWT provenance (adapter transport-complete, no Phase-1 consumer).
- 10-message cap: hard soft-close implemented; §9's "conversation number" prompt-side variant still [CONFIRM] with owner.
- Decision values marked for review: RAG (k=25/RRF 60/context 5/no reranker), eval thresholds (0.7–0.9 per metric), judge LLM = `claude-opus-4-8`.
- **Ledger PDF date-window cap = today+7 [CONFIRM]** — spec §2.5 contrasts "today+7 vs today" but never states Ledger's cap; contracted as today+7 pending owner confirm.
- **Tax Intent split (Gate-1 decision)** — the frozen Intent enum encodes the flow spec's "one spine, three intents": `report_tax` / `report_capital_gain` / `report_tax_pnl`, all registering to the single tax FlowDefinition (preserves routing telemetry granularity). Alternative: collapse to one `report_tax`. Owner picks at Gate 1; the enum freezes with Wave 0.
- `app/store/migrations/runner.py` is contracts-foundation-owned; conversation-store-writer treats it as **read-only** (its 0002+ files are applied by, never modify, the runner).

## 6. Worktree queue & merge/rebase order (max 4 concurrent, per CLAUDE.md)

Wave 0 lands serially. Wave 1 fans out through a 4-slot worktree queue,
highest-risk / most-depended-on first; a slot frees on merge and the next
change in the queue takes it. Every proposal has a machine-readable
`manifest.yaml`; the reconcile pass computed zero filesTouched intersections
(sole blessed exception: the `app/main.py` stub→orchestrator handoff), so any
merge order inside Wave 1 is conflict-free — the order below just minimizes
integration wait.

| Queue slot order | Change | Why this position |
|---|---|---|
| 1 | finx-http-adapters | 5 auth schemes; flows integration-verify against it |
| 2 | flow-engine-runtime | everything flows through `advance()` |
| 3 | widget-shell | longest UI tail; fully mock-driven |
| 4 | llm-router | orchestrator's first fake→real swap |
| 5 | rag-service | needs contracts' DB factory; second swap |
| 6 | conversation-orchestrator | replaces the main.py stub; wire hub |
| 7 | ticketing-freshdesk | third swap |
| 8 | conversation-store-writer | migrations 0002 lands after 0001 is proven |
| 9 | tracing-observability | consumers decorate later regardless |
| 10–15 | flow-pnl · flow-tax-report · flow-contract-notes · flow-ledger-mtf · flow-cml · flow-brokerage | small, disjoint; tax first (best-specified), MTF later ([CONFIRM] pending) |
| 16 | eval-harness | full runs only make sense near assembly |

Rebase rule (CLAUDE.md post-merge step): every open worktree rebases onto new
main immediately after each merge. Since filesTouched sets are disjoint,
rebases are mechanical; a conflict during rebase is a plan error — escalate,
don't hand-resolve silently.

Wave 2 integration is sequenced by the orchestrator worktree: swap one fake at
a time (router → engine+flows → rag → ticketing), running the eval-harness
blocker gate after each swap.
