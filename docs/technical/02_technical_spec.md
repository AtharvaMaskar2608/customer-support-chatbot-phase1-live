# Jini Customer Support Chatbot — Technical Specification (Phase 1)

> **Status: DRAFT v0.2 (2026-07-16)** — consolidated source of truth that
> OpenSpec change proposals will be written against. Detailed per-endpoint API
> reference lives in `03_finx_api_reference.md` (in progress).

## Document map

| Section | Source docs | Status |
|---|---|---|
| 1. Product scope | `customer_support_chatbot_phase1.md` | ✅ |
| 2. Architecture | `customer_support_chatbot_phase1.md` (flow spec) | ✅ |
| 3. Data model | `rag_guide/1`, `tracing/1-2`, project memory | ✅ |
| 4. FinX API integration | `finx_api_reports_documentation.md` + 2026-07-16 live captures | ✅ (detail → `03_finx_api_reference.md`) |
| 5. RAG pipeline | `rag_guide/1-3` | ✅ |
| 6. Tracing & observability | `tracing/1-2` | ✅ |
| 7. Evaluation | `rag_guide/2-3`, `chatbot_eval/1-3`, test-case xlsx | ✅ |
| 8. Widget / UI surface | `Jini Widget Screens.html`, `contract-note-flow-screens (1).html`, owner decisions | ✅ |
| 9. Open questions & gaps | all | ✅ |

---

## 1. Product scope

**Choice Jini** — an agentic customer-support chatbot for **FinX** (Choice
India's trading platform), shipped as a React web page in a WebView (FinX
Android/iOS app) and a floating window (FinX website). Goal: offload the human
support team by (a) directly fulfilling report requests and (b) answering
explanatory/process questions.

**Audience**: logged-in FinX retail trading clients. The widget is
**post-login** and inherits the app's auth — this is the core design premise
(it eliminates the "verification required from registered email" friction that
appears in every support-ticket cluster).

**Two Phase-1 capabilities**:
1. **11 report flows** — deterministic hardcoded flows; the LLM only
   classifies intent and collects params (segment, date range, FY, format).
2. **RAG function** — explanation/process questions (e.g. brokerage charges),
   over the existing `qa_chunks` KB.

Cross-cutting: **Freshdesk raise-ticket tool** and a **call-support chip**
(number + timings), both always reachable; the call chip stays visible even
after a ticket is raised.

### 1.1 "Phase 1" is overloaded — three senses

| Sense | Meaning |
|---|---|
| Whole build | "Phase 1 – Live": widget + 11 report flows + RAG + ticketing + conversation store + tracing |
| Personalization tier | Phase 1 greets by **Client ID** (`X008593`); Phase 2 upgrades to first name via get-profile |
| Test-plan phasing | Test spreadsheet: Phase 1 = **KB/RAG-only, no API**; Phase 2 = RAG + API flows |

⚠️ The UI mockups all show API-integrated (test-plan "Phase 2") behavior;
there is no KB-only mockup. Confirm the intended launch sequencing.

**Non-goals / later**: first-name personalization; Haiku model toggle; no
standalone Capital-Gain API (folded into Tax Report); no bulk contract-note
download (bulk = email only); no computed rupee brokerage figure (rates only,
point to contract note).

## 2. Architecture

### 2.1 Components

- **Frontend**: React in WebView (app) / floating window (web). Two entry
  surfaces: Main/Support entry (greeting + 4 starter chips) and Reports-screen
  entry (intent-based, pre-scoped, fulfilment-only chips).
  **Decision (2026-07-16): entry screen variant 1a; P&L flow variant 2a.**
- **Backend**: Python / FastAPI (locked).
- **LLM layer**: Claude (Anthropic). **Pinned 2026-07-16: `claude-sonnet-5`**
  (the flow spec's "sonnet-4-6" is not a real ID); backend-configurable
  toggle target `claude-haiku-4-5-20251001`.
- **Tool layer**: the FinX report APIs + Freshdesk raise-ticket as agent tools.
- **RAG subsystem**: OpenAI embeddings + pgvector; generation by Claude.
- **Conversation store**: PostgreSQL, written after every bot response by a
  separate thread (schema undefined — design task, see §3.2).
- **Tracing**: DeepEval `@observe` on every turn/decision/tool call; optional
  Confident AI export; intended to later feed fine-tuning.

### 2.2 Flow-engine + LLM-router split (core design)

A **deterministic flow engine gated by a thin LLM router**:

- **LLM router**: classify utterance → intent (report flow / RAG / ticket);
  extract params already present in free text (FY, dates, segment, format);
  ask follow-ups **only when genuinely ambiguous**.
- **Flow engine**: once intent is known, a hardcoded state machine drives
  fulfilment — segment/date/FY/format steps as tappable stepper cards with
  chips, deterministic API call, byte validation, file-card delivery. The LLM
  never improvises the fulfilment path.
- **Guardrails are per-module and externalized** (JSON/dict/class config, not
  in code), same for chips and prompts.

### 2.3 Conversation lifecycle

1. User opens FinX → chat. App passes context via **URL query params**:
   `userId`, `sessionId`, `accessToken` (JWT), `isDarkTheme`, `platform`,
   `page`.
2. Backend calls get-profile (Phase 2 personalization; Phase 1 shows Client ID).
3. Widget shows time-aware greeting + 4 configurable chips + free text.
4. First user action = first message → LLM router classifies → report flow /
   RAG / ticket.
5. Flow engine collects params via stepper chips (≤2 follow-ups), calls the
   FinX API **server-side**.
6. File reports: backend fetches the report URL server-side, **validates bytes
   (size floor + magic bytes)**, delivers bytes as a chat file card — the
   (often unauthenticated) URL never reaches the client or logs.
7. After every bot response, a separate thread writes the turn to PostgreSQL;
   DeepEval traces it.

### 2.4 Caps & escalation

- **10 messages/conversation** cap (owner leaning to a soft prompt-side
  guardrail with a "conversation number" — undecided, see §9).
- **≤2 follow-up questions** per disambiguation.
- At cap / unresolved → offer raise-ticket (Freshdesk, transcript in
  description) and/or call-support chip.
- Visible compliance footer: **"Factual answers only — never investment
  advice."**

### 2.5 Bot-internal contracts (from the flow spec)

- `currentFY(today) -> "YYYY-YYYY"`; `start = today.month>=4 ? year : year-1`;
  `supportedFYs = [currentFY, -1, -2]`; `defaultFY = currentFY - 1`
  (pre-highlighted). Rolls forward every 1 April — **never hardcode the three
  years**. Single mapping fn for `FY 2025-26` ↔ `"2025-2026"`.
- **AY→FY** conversion with explicit user confirmation.
- **Byte validation** before every delivery; on failure → one silent
  auto-retry (fresh generation) → then E-FETCH error bubble.
- **Per-flow byte/selection cache**, 15-min TTL, session-scoped; "send it
  again"/"resend" always bypass the cache.
- Intent precedence: "tax" beats "p&l"; "capital gain/CG" → Tax Report; bare
  "P&L" → P&L; "holding statement" → Holding (not Ledger).
- **Per-flow date windows differ by design — do not unify**: Ledger floor
  2019-01-01; Contract Note / Global Detail / P&L floor 2018-01-01; caps
  `today+7` vs `today`; P&L has a 2-year max-range clamp, Ledger/Global Detail
  none.

### 2.6 Hard rules (compliance & safety)

- Post-login only; reuse app JWT/session tokens from URL params.
- Report URLs / `file_id`s / server filenames never exposed to client or logs;
  display filenames renamed (server names leak ClientId) — **exception: CML
  keeps the server's own `Client_Master_List.pdf` name** (contains nothing
  sensitive, per the flow spec).
- ⚠️ **CML URL 120s/single-use is NOT a real security boundary** (live testing
  2026-07-16 — CloudFront path-only caching defeats it; see
  `03_finx_api_reference.md` §7 FLAG B). Always fetch server-side; never rely
  on the URL expiring.
- ⚠️ **Contract Note endpoint enforces no auth** (§7 FLAG A) — the Jini
  backend MUST gate `client_id` by the widget's authenticated session; never
  pass a user-supplied client_id straight through.
- Errors are **conversational bubbles with recovery chips, never toasts**;
  date pickers hard-disable invalid ranges rather than validate after; user
  copy never exposes `Reason`/HTTP codes/URLs (log `Reason` server-side).
- Email delivery only to the **registered email**, masked
  (`san***.harsha@gmail.com`), not editable in-bot.

## 3. Data model

### 3.1 RAG knowledge base (exists — reuse, don't rebuild)

- Table **`qa_chunks`**, PostgreSQL + pgvector: **1,102 rows, 3072-dim**
  embeddings (`text-embedding-3-large` full size). Reachable via SSH tunnel
  or prod.
- Single queryable text column `chunk` = `Query -> Solution -> TAT`
  concatenation (TAT = turnaround time). Hybrid = FTS + vector over it.
- Token stats: max 653, mean 58.68 → no sub-chunking.
- **3072-dim exceeds pgvector's 2000-dim ANN index cap** → sequential scan
  (exact, fine at 1,102 rows). To scale later: Matryoshka-truncate ≤2000 dims.
  Cosine distance throughout.

### 3.2 Conversation store (undefined — explicit Phase-1 design task)

Requirement: after every bot response a separate thread inserts the turn into
PostgreSQL. Owner quote: "Need help deriving the structure of the table too."

Natural columns (derived from the tracing model): `thread_id`, `turn_id`,
`user_id` (Client ID), user message, assistant message, detected intent, tool
calls + args + results, retrieval context, timestamps, latency/token usage,
model version, turn number (for the 10-msg cap). Must capture decisions and
tool traces (not just final text) to serve future fine-tuning.

### 3.3 Trace model

Trace = one request lifecycle; Span = one call (typed agent/retriever/llm/
tool); Thread = traces sharing `thread_id` = one conversation. App owns state;
DeepEval only observes. **PII masking mandatory** (names, emails, Client IDs,
ledger amounts) via `mask=` in `trace_manager.configure`.

## 4. FinX API integration

> **Update 2026-07-16**: new live captures supersede parts of this section.
> The originally documented data APIs don't support both PDF download AND
> email; the owner's decision is to use the newly captured `*PDF` report
> endpoints (`GetGlobalPNLPDF`, `GetLedgerDetailsPDF`, `GetTaxReportPDF`,
> CML via `POST /mis/reports/generate` with JWT auth) for those flows, and
> the main documented data APIs for the rest of the 11 flows. See the
> detailed API reference: `docs/technical/03_finx_api_reference.md`.
> Notables from the captures: `RequestFor` 0=download/1=email on
> `GetGlobalPNLPDF` (but 2 observed on Tax; Android enum says Mail=1,
> Download=2 — semantics differ per endpoint, reconcile); `With_Exp` sent as
> boolean `true` (docs showed int 1); Ledger PDF uses `Group:"GROUP1"`
> (uppercase), `LoginId=<client code>` (not "JIFFY") and a new `Margin` field
> (0 observed — likely the missing MTF discriminator); a **third backend**
> `/mis/reports/generate` authenticates with the SSO JWT (`authType: jwt`,
> `source: FINX_ANDROID`), not the SessionId.

FinX is the Choice India brokerage backend. 8 documented endpoints across 5
functional areas (Ledger, Global PNL, Detailed PNL, Contract Notes, Tax Report),
served by **two distinct middleware backends** with different conventions. All
requests are `POST` with `Content-Type: application/json`.

**Cross-cutting rule: errors are in-band.** Every endpoint returns HTTP `200 OK`
regardless of outcome. Branch on the body (`Status` / `StatusCode`), never on
the HTTP status code.

### 4.1 Two backends, two conventions

| Aspect | `/api/middleware` (legacy .NET-style) | `/middleware-go` (Go service) |
|---|---|---|
| Field casing | PascalCase (`ClientId`, `FromDate`) | snake_case (`client_id`, `from_date`) |
| Envelope | `{ Status, Response, Reason }` | `{ StatusCode, Message, DevMessage, Body }` |
| Success indicator | `Status: "Success"` | `StatusCode: 200` |
| No-data indicator | `Status: "Fail"`, `Response: null` | `StatusCode: 204`, `Body: {}` |
| Auth | `authorization` header **+ `SessionId` duplicated in JSON body** | `authorization` header only |
| Endpoints | All except Contract Notes | Contract Notes only |

Base URLs: `https://finx.choiceindia.com/api/middleware`,
`https://finx.choiceindia.com/middleware-go`.

### 4.2 Authentication & session mechanics

- Auth = **SessionId** in the `authorization` HTTP header on every request.
- On `/api/middleware` endpoints the same SessionId must ALSO appear in the JSON
  body as `SessionId`; on `/middleware-go` it goes in the header only.
- Success responses carry an `authstatus: Authorized` response header.
- **No login/refresh endpoint is documented.** SessionId acquisition, lifetime,
  and expiry behavior are unknown — biggest integration blocker (see §9).
- Some endpoints send `from: Web_finx.choiceindia.com_V_4.6.0.4` (Detailed PNL,
  Contract Notes, Tax Report); necessity unverified.
- Identity fields are **inconsistent per endpoint** — see §4.8 trap list.

### 4.3 Ledger — `POST /api/middleware/GetLedgerDetails`

Covers both standard ledger and (nominally) MTF ledger.

**Request contract** (all required):

```json
{
  "LoginId": "JIFFY",
  "ClientId": "<client code, e.g. X493657>",
  "Group": "Group1",
  "FromDate": "YYYY-MM-DD",
  "ToDate": "YYYY-MM-DD",
  "SessionId": "<session id>"
}
```

**Response contract**: `Response` = array of ledger records. First record on a
full-period query is the `OPENING` voucher. Date ranges align to the Indian
financial year (Apr 1 – Mar 31).

Record fields: `trd_Date` (ISO datetime; `1900-01-01T00:00:00` = null sentinel
on the opening row), `vDate`, `voucher` (e.g. `"OPENING"`), `Trans_Type`
(`"O"` = opening), `No`, `Code`, `Narration`, `ChqNo`, `Debit`, `Credit`,
`settlement_No`, `Mkt_Type` (NSE/BSE segment), `FinStyr`, `dt`.

⚠️ **MTF ledger**: on this DATA endpoint the captured MTF request is
byte-identical to the standard ledger call — no discriminator known here.
However, the delivery endpoint `GetLedgerDetailsPDF` carries a `Margin` field
(`0` captured on normal ledger; `1` = MTF hypothesis) — the likely
discriminator. See `03_finx_api_reference.md` §4.2/§5; one MTF capture still
needed to confirm.

### 4.4 Global PNL data (segment-level) — `POST /api/middleware/GetGlobalPNLNew`

> **Data-only endpoint — NOT the delivery endpoint.** The P&L report flow
> delivers files via `GetGlobalPNLPDF` (see `03_finx_api_reference.md` §4.1).
> This endpoint returns P&L *records* and is only needed if the bot ever
> renders P&L numbers in-chat or detects empty ranges.

One endpoint; segment selected via `Group`: `"Cash"` (equity), `"Derv"` (F&O),
`"Comm"` (commodity).

**Request contract**:

```json
{
  "UserId": "<client code — NOT 'JIFFY'>",
  "ClientId": "<client code>",
  "Group": "Cash | Derv | Comm",
  "FromDate": "YYYY-MM-DD",
  "ToDate": "YYYY-MM-DD",
  "With_Exp": 1,
  "SessionId": "<session id>"
}
```

`With_Exp: 1` = include charges (0 presumed to exclude; unverified).

**Response contract**: only the no-data shape is captured:
`{ "Status": "Fail", "Response": null, "Reason": "Data not found." }`.
**Success schema undocumented** — requires a trade-bearing capture before any
parsing/rendering code is written.

### 4.5 Detailed PNL (scrip/transaction-level) — `POST /api/middleware/GetDetailedPNL`

Segments: `Group: "Group1"` (equity/default), `"Group23"` (commodities).
Note the two Group vocabularies: Global PNL uses `Cash/Derv/Comm`; Ledger and
Detailed PNL use `Group1/Group23`. Not interchangeable.

**Request contract**:

```json
{
  "UserId": "neuron",
  "ClientId": "<client code>",
  "Group": "Group1 | Group23",
  "FromDate": "YYYY-MM-DD",
  "ToDate": "YYYY-MM-DD",
  "SessionId": "<session id>"
}
```

`UserId` is the **fixed literal `"neuron"`** here. No `With_Exp` field.
Sends the `from:` version header.

**Response contract**: only no-data captured. **Success schema undocumented.**

### 4.6 Contract Notes — `POST /middleware-go/report/contract` (Go backend)

**Request contract** (snake_case, no SessionId in body):

```json
{
  "client_id": "<client code>",
  "from_date": "YYYY-MM-DD",
  "to_date": "YYYY-MM-DD"
}
```

**Response contract**: `{ StatusCode, Message, DevMessage, Body }` where
`StatusCode` is an HTTP-style semantic code (200 success, 204 no content),
`Body` = payload (`{}` when empty). Success `Body` wire field names are still
uncaptured, but the UX spec fixes the semantic shape: a **list of notes keyed
by `file_id`** (unique per note, the download handle — dual-note days share a
date but have two `file_id`s), each with trade date + segment (`Grp1` →
"Equity & F&O", `MCX` → "Commodity"; no other groups). The per-note download
endpoint (`file_id` → PDF URL) is still uncaptured. See
`03_finx_api_reference.md` §4.4.

### 4.7 Tax Report — `POST /api/middleware/GetTaxReportPDF`

**Request contract**:

```json
{
  "ClientId": "<client code>",
  "FinYear": "2025-2026",
  "RequestFor": 2,
  "FileFormat": 1,
  "SessionId": "<session id>"
}
```

- `FinYear`: current + last two FYs (dynamic — never hardcode; see §2.5).
- `RequestFor`: `2` = download-here, `1` = email (ViewType-compliant — Tax
  only; other `*PDF` endpoints use `0` for download, see
  `03_finx_api_reference.md` §2).
- `FileFormat`: `1` = PDF, `2` = Excel (Excel confirmed by 2026-07-16
  capture).
- Breaks the common pattern twice: takes `FinYear` instead of a date range, and
  `Response` is a **string file URL**, not an array:
  `https://client-report.choiceindia.com/PDFReports/TaxReport_<REPORT_ID>_<ClientId>.pdf`

🔒 **Security**: the generated URL appears unauthenticated once created —
anyone with the link can fetch the report. Treat as sensitive; do not log or
echo freely; consider proxying rather than surfacing raw URLs to users.

### 4.8 Integration trap list (chatbot-side requirements)

1. Branch on body `Status`/`StatusCode`, never HTTP status.
2. Two parsers required — one per backend envelope/casing; don't build one
   generic parser.
3. Duplicate `SessionId` into the body for `/api/middleware`; omit for
   `/middleware-go`.
4. Identity field per endpoint: Ledger → `LoginId="JIFFY"`; Global PNL →
   `UserId=<client code>`; Detailed PNL → `UserId="neuron"`; Contract Notes →
   `client_id`.
5. Dates: `YYYY-MM-DD`, Indian FY aligned (Apr 1–Mar 31); Tax Report uses
   `FinYear` `YYYY-YYYY`.
6. Treat Tax Report URLs as sensitive/unauthenticated.
7. Re-capture live responses to fill success-schema gaps before rendering
   PNL / Detailed PNL / Contract Notes data.

## 5. RAG pipeline

> Source split: `rag_guide/1_building_rag_pt1.md` is **our own design doc**
> (its decisions are binding); `rag_guide/2-3` and `tracing/1-2` are DeepEval
> vendor docs (binding as to tool/API choice, but their numeric example values
> — `chunk_size=1024`, `k=5`, `threshold=0.7` — are tutorial illustrations,
> not project mandates).

### 5.1 Binding decisions

- **Engine**: PostgreSQL + `pgvector` (hard prerequisite). Hybrid RAG =
  Full-Text Search + Vector Search over the same data.
- **Chunk schema**: a single queryable column named `chunk`; everything
  retrievable must live in that column.
- **Chunk composition**: one chunk per KB entry, concatenating
  `Query -> Solution -> TAT` in that order.
- **Embedding model**: the guide frames large-vs-small as an experiment axis,
  but the existing KB is embedded at **3072-dim = `text-embedding-3-large`
  full dimension**, and query vectors must match the stored dimension —
  so query-time embedding is **effectively locked to
  `text-embedding-3-large` @ 3072** unless the KB is re-embedded into a
  parallel column. Do not wire `-small` (1536-dim) or truncated vectors
  against the current KB.
- Matryoshka truncation (`dimensions=` request param, e.g. 256) is an optional
  storage/speed trade-off.

### 5.2 KB token statistics (measured)

Max 653 tokens, mean 58.68 per chunk — well within embedding input limits, so
**no sub-chunking needed**.

### 5.3 Vector index selection

| Option | When | Notes |
|---|---|---|
| Sequential scan (no index) | < ~100k rows or narrow `WHERE` filter | Exact, 100% recall, O(n); supports up to 16000 dims |
| IVFFlat | Larger tables, cheaper build | `lists = rows/1000` (≤1M rows), `probes ≈ lists/10`; data must be loaded first; `REINDEX` after bulk growth |
| HNSW | Best general speed/recall | `m=16`, `ef_construction=64`, `ef_search=40`; constraint `ef_search ≥ LIMIT` |

All examples use cosine distance (`vector_cosine_ops`, `<=>`).

⚠️ **Dimension cap**: HNSW and IVFFlat support **≤ 2000 dims**; the existing
KB is 3072-dim. At 1102 rows, **sequential scan is the correct choice** and
sidesteps the conflict (needs to be confirmed as an explicit decision — see §9).

### 5.4 Not yet specified (must be decided before implementation)

- **Top-K** — never fixed in any doc (tutorials use k=5).
- **FTS half of "hybrid"** — asserted but never implemented: no `tsvector`
  setup, no `ts_rank`, no fusion strategy (e.g., RRF) documented.
- **Reranker** — listed as a pipeline step and measured by
  `ContextualPrecisionMetric`, but no model/service chosen.

## 6. Tracing & observability

Tool: **DeepEval `@observe` tracing**, optional Confident AI export (works
fully offline without it).

### 6.1 Core model

- **Trace** = one request lifecycle; **Span** = one function call (spans nest
  automatically from the call stack); **Thread** = traces grouped by shared
  `thread_id` (a conversation/session).

### 6.2 Setup contract

`trace_manager.configure(openai_client=..., confident_api_key=...,
environment="development|staging|production", sampling_rate=1.0, mask=<PII fn>)`

- Auto-patching intercepts OpenAI `chat.completions.create` and (per the
  tracing guide's prose) Anthropic `messages.create` — captures model, tokens,
  messages with no manual work. ⚠️ **Caveat**: the documented `configure()`
  signature only shows an `openai_client=` param — verify the installed
  DeepEval version exposes an Anthropic hook; if not, log Claude calls
  manually on the `llm` span (`update_llm_span()` path for unsupported
  clients).
- `sampling_rate` 1.0 in dev, lower in prod. `mask` = PII-redaction hook
  applied before export (policy undecided — see §9).

### 6.3 Instrumentation contract

- `@observe(type="agent"|"retriever"|"llm"|"tool", metrics=[...],
  metric_collection="...")` — **always set `type`**; typed spans unlock
  component-specific metrics.
- `update_current_span(input, output, retrieval_context: list[str], metadata,
  ...)` — `retrieval_context` is **required for RAG metrics**.
- `update_current_trace(name, tags, metadata, thread_id, user_id, input,
  output, test_case, metric_collection, ...)`.
- Canonical shape: root `answer_user_query()` (agent) → `retrieve_context()`
  (retriever) → `generate_response()` (llm).

### 6.4 Multi-turn tracing

- No start/end-conversation API — trace each turn, stitch with the same
  `thread_id` via `update_current_trace()`; generate `thread_id` once per
  session (`uuid4`), persist alongside history.
- **Conversation state is the app's responsibility** — DeepEval observes only.
- Per-turn retrieval context goes on each turn's retriever span.
- Post-session scoring: `evaluate_thread(thread_id, metric_collection)` —
  fits support flows with a clear end state.

### 6.5 Production rules

- Never run local LLM-judge metrics in prod (blocking latency); use
  `metric_collection=` for async Confident AI evaluation instead.
- Long-running servers: periodically `trace_manager.clear_traces()`;
  short scripts: `CONFIDENT_TRACE_FLUSH=1`.

## 7. Evaluation

Tool: **DeepEval** (+ optional Confident AI platform).

### 7.1 Synthetic test data

`Synthesizer().generate_goldens_from_docs(document_paths, chunk_size=1024,
chunk_overlap=0, max_contexts_per_document=3, num_evolutions, evolutions)`
produces **Goldens** (test cases without `actual_output`/`retrieval_context`
— filled at eval time by running the app). `generate_goldens_from_contexts()`
skips doc loading/chunking.

- **7 evolution types** for edge-case coverage: REASONING, MULTICONTEXT,
  CONCRETIZING, CONSTRAINED, COMPARATIVE, HYPOTHETICAL, IN_BREADTH
  (first six = depth, IN_BREADTH = topic breadth).
- Auto-quality gates: context chunks scored on Clarity/Depth/Structure/
  Relevance (avg ≥ 0.5, ≤3 retries); synthetic inputs scored on
  Self-containment/Clarity.
- ⚠️ The synthesizer `chunk_size=1024` default is a *different* "chunk"
  concept from our ~59-token retrieval chunks — don't conflate; the default
  may under-generate contexts on our KB.

### 7.2 Single-turn RAG metrics — score retriever and generator separately

| Metric | Component it diagnoses | Needs labels? |
|---|---|---|
| `ContextualPrecisionMetric` | Reranker (ranking order) | Yes (`expected_output`) |
| `ContextualRecallMetric` | Embedding model | Yes |
| `ContextualRelevancyMetric` | Chunk size + top-K | No |
| `AnswerRelevancyMetric` | Prompt template | No |
| `FaithfulnessMetric` | Generation LLM (hallucination) | No |
| `GEval(criteria=...)` | Custom (e.g., correctness) | Configurable |

"RAG triad" (referenceless): AnswerRelevancy + Faithfulness +
ContextualRelevancy. Test-case contract:
`LLMTestCase(input, actual_output, expected_output, retrieval_context)` —
`input` is **raw user input only**, never the full prompt template.

### 7.3 Multi-turn evaluation

Retrieval happens **every turn**; failure modes: context drift, redundant
retrieval, cross-turn hallucination. Turn-level metrics:
`TurnContextualPrecision/Recall/Relevancy`, `TurnFaithfulness`, plus
`KnowledgeRetentionMetric`, `TurnRelevancyMetric`, `RoleAdherenceMetric`.
Contract: `ConversationalTestCase(expected_outcome, turns=[Turn(role, content,
retrieval_context)])` — retrieval context lives on each **Turn**.
`ConversationSimulator(model_callback=...)` auto-generates conversations.

**Simulation approach** (`chatbot_eval/1-3`): you can't pre-write expected
outputs for multi-turn — test against **scenarios**. Objects:

- `ConversationalGolden(scenario, expected_outcome, user_description)` —
  persona-driven test seed; `expected_outcome` doubles as the stop signal.
- `ConversationSimulator` — loops simulated-user-msg → call app → check
  outcome, until done or `max_user_simulations` (docs suggest 4–8). The
  integration seam is the async `model_callback`; returning
  `retrieval_context` and `tools_called` on each `Turn` is what unlocks RAG
  and tool metrics — **required plumbing, not optional**. A pattern exists to
  seed with Jini's standing greeting turn.
- Output = `ConversationalTestCase(turns=[...])` → `evaluate()`.

**Metric catalog** (all referenceless unless noted; examples use 0.7):
`ConversationCompletenessMetric` (headline: satisfied/total intentions),
`TurnRelevancyMetric`, `KnowledgeRetentionMetric`, `RoleAdherenceMetric`
(needs `chatbot_role`), `TopicAdherenceMetric` (needs `relevant_topics`),
`GoalAccuracyMetric` + `ToolUseMetric` (agentic; need `tools_called` /
`available_tools`), Turn-level RAG metrics (§ above), `ConversationalGEval`
(e.g. "never gives investment advice"), `ConversationalDAGMetric`.

**Workflow**: dev loop = ≥20 diverse goldens → simulate → metrics → iterate.
Prod loop = log threads by `thread_id` → async metric-collection eval → feed
failures back as new goldens. **Anti-pattern (flagged twice)**: don't replay
historical prod conversations as benchmarks.

### 7.4 Manual test plan (`Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx`)

- **Phase 1 sheet** (KB/RAG-only, **no API**): 41 cases A1–E12 —
  A retrieval accuracy (incl. Hindi/Hinglish/vernacular/typos),
  B grounding (B3 blocker: never invent numbers → FD ticket),
  C hallucination & safety (mostly blockers: investment-advice refusal,
  prompt-injection resistance, no fabrication),
  D confidence & escalation (D3 blocker: follow up twice then escalate,
  never guess; D4 blocker: no-match → agent handoff),
  E conversation quality (≤3 short paras, language stickiness, tone).
- **Phase 2 sheet** (RAG + API): 47 cases F1–M3 — intent routing, API
  transactional (G1/G5 blockers incl. AuthToken → right client only), API
  error handling (H8 blocker: no stack-trace leak), data correctness (I1–I3
  all blockers: **no cross-client leakage**, exact period, figures match
  backend), multi-intent & 10-cycle soft close, ticket & handoff (duplicate
  prevention, open-ticket awareness), session keywords (RESTART/END, 5-min
  nudge, 15-min hard close, 30-min absolute cap), M regression re-runs
  Phase 1.
- **Severity model**: single Blocker failure holds launch. Phase 1 blockers:
  B3, C1–C3, C5–C8, D3, D4. Phase 2 blockers: F7, G1, G5, H8, I1–I3.
- Hidden contracts in tester notes: B3 numeric-gap → ticket flow; language
  stickiness rule (English once → English thereafter); C4 and E6 deferred.
- ⚠️ README claims 36/46 cases; sheets actually contain 41/47 — reconcile.
- **No machine-runnable Golden set exists yet** — authoring ≥20
  `ConversationalGolden`s is an open task; the spreadsheet is human QA
  scaffolding.

### 7.5 CI/CD and experiment tracking

- `assert_test(test_case, metrics)` parametrized over a dataset, run via
  `deepeval test run` — failing scores break the build.
- `@deepeval.log_hyperparameters(model=..., prompt_template=...)` logs config
  (embedding model, chunk size, k, temperature) for grid-search comparison.
- **No numeric pass/fail thresholds are mandated anywhere** — tutorial values
  (0.7/0.8) only. Project thresholds are an open decision.

## 8. Widget / UI surface

WhatsApp-style chat widget "Choice Jini" (avatar ✦, "● online · <ClientId>",
"↺ Start over"). Web: floating ~400×640 window bottom-right, collapses to a
bubble, unread badge, position persists. App: full-screen slide-up (280ms)
from "Help & Support → Ask Choice Jini", swipe-down dismiss.

**Chosen variants (owner decision, 2026-07-16): entry screen 1a (Support
section: greeting + "Popular right now" chips + free text) and P&L flow 2a
(stepper card).** The Reports-screen entry (1b) remains as the second entry
surface per the flow spec.

### 8.1 Design tokens (FinX theme)

Primary `#2B6BE8`, positive `#17B26A`, text `#1A1D21`/`#5F6B7A`, chip surface
`#F7F9FC` + border `#D5DCE6`.

**Font (DECISION 2026-07-16): use the native system font stack**, matching the
HTML mockups. The mockups do **not** name a custom brand typeface (the only
real `font-family` declarations are `-apple-system, BlinkMacSystemFont,
sans-serif` for UI and `ui-monospace, Menlo, monospace` for code — earlier
"Inter/Lato" sightings were substring false-positives). So Jini ships with the
system stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
sans-serif`. If FinX later provides a brand typeface, it's a token swap.

### 8.2 Required UI primitives

User/bot bubbles; **editable multi-step stepper cards** (completed steps stay
tappable); in-chat calendar with **hard-disabled** out-of-range dates; file/PDF
cards ("182 KB · PDF · password: PAN" + "Trouble opening it? Tell me." helper —
targets a measured 308-ticket attachment-clarity cluster); **paginated
note-list card** (contract notes: 10/page, month dividers, segment badge
NSE·BSE vs MCX only when a day has two notes, rows keyed by `file_id`);
quick-reply chips; conversational error bubbles with recovery chips (never
toasts); "Generating…" indicator when >5s.

### 8.3 Flow specifics

- **P&L (2a)**: Segment (Equity/F&O/Commodity) → date range → delivery
  (PDF here / email). Calendar floor Jan 2018, cap today+7, max 2-year range.
  Free-text parse pre-fills a confirm card; out-of-range → "I can fetch from
  Jan 2018 onwards…". PDF password = PAN. Email to masked registered address.
- **Contract notes**: per-trading-day list primitive; calendar floor 2018,
  cap **today**, no max range; **no PDF password**; bulk = email-all only;
  narrow-nudge at 50 notes; download failure → one silent retry.
- **What's New**: remote-config driven (`whats_new`, 24h cache, ≤3 items,
  optional `min_app_version`), red-dot badge per client code, never
  auto-popup; CTAs can deep-link a prefilled prompt.
- All limits (page size 10, threshold 50, calendar bounds, chips) are
  **remote-config**, shared across both entries.

### 8.4 Shared cross-flow content contracts

These are shared contracts reused by every flow — implement once, as config.

**Error taxonomy** (conversational bubbles + recovery chips, never toasts;
copy verbatim from the flow spec §7):

| Code | Trigger | Bubble copy | Recovery chips |
|---|---|---|---|
| `E-NODATA` | API failure meaning no data in range (only failure `Reason` confirmed by product) | "No transactions found for FY {FY_short}, so there's nothing to report for that year." | Try FY {defaultFY} (or another in-window year) · 🎫 Raise a ticket |
| `E-YEAR` | Requested FY outside window (no API call made) | "I can pull Tax Reports for the current and last two financial years — that's {list}. Which one?" | The 3 FY chips |
| `E-TIMEOUT` | API or byte-fetch timeout / network failure | "That took longer than it should — the report didn't come through. Your selections are saved." | ↺ Retry · 🎫 Raise a ticket |
| `E-FETCH` | `Status: Success` but URL 404s / empty / wrong magic bytes | "The report generated but arrived incomplete on my side — let me redo it." (one silent auto-retry; if retry fails →) "Still not coming through cleanly." | ↺ Try again · ✉️ Email me both · 🎫 Raise a ticket |
| `E-UNKNOWN` | Any other `Status != "Success"` | "Something went wrong generating that report on our side." | ↺ Retry · 🎫 Raise a ticket |

Rules: never expose `Reason`/HTTP codes/URLs in copy; log `Reason` verbatim
server-side; `E-FETCH` auto-retries once silently before showing the bubble's
second line.

**Partial dual-format email failure (EC-12, all email-capable flows)**: tell
the truth — "Your PDF is on its way to {masked_email}, but the Excel didn't go
through." Chips: ↺ Retry Excel · 📊 Get Excel here · 🎫 Raise a ticket.

**Greeting pool** (rotate, time-aware; Phase 1 uses Client ID):

- Default: "Hey X008593 — what do you need?"
- Morning (06:00–09:00): "Good morning, X008593 ☀️ What can I get for you?"
- Market hours (09:15–15:30): "Hi X008593 — markets are live. Need a report
  or a quick answer?"
- Post-market (15:30–23:00): "Hi X008593 👋 Markets are closed — I'm not."

**Entry-2 (Reports screen) contract**: default message "Which report do you
need, X008593? Pick one below or just type — I'll deliver it here as PDF or
Excel." Chips (fulfilment only, by ticket volume): 📊 P&L Statement ·
📒 Ledger · 📁 Holding Statement · 🧾 Tax Report. Input placeholder rotates
the long tail: "or type: CML, Contract Note, Capital Gain, Global…" (covers
report sub-types 5–11 without breaking the 4-chip limit).

**Stepper edit semantics**: tapping a completed step reopens it and clears
downstream selections; the prior file card stays in chat history; nothing is
re-fetched until generation; cache is keyed per selection so no
cross-contamination.

**Brokerage render contract** (endpoint captured — `03` §4.6c): a card built
**dynamically** from the `get-brokerage-slab` response — an array of segment
groups `{title, list:[{title, desc}]}`. Render `desc` verbatim (pre-formatted
rate text like "₹0.10 for trade value of 10 thousand"); never compute a rupee
figure; no PDF/email. **Slabs differ per client — do not hardcode the segments
or row count**; iterate whatever the API returns.

### 8.5 Language & tone

English/Hindi/Hinglish; sticky-language rule (English once → English
thereafter); warm, concise, ≤3 short paragraphs; persistent "Factual answers
only — never investment advice" disclaimer; "Files land right here — no email
verification."

## 9. Open questions & gaps

### Status after API test phase (2026-07-16)

**Discovery + spec phase: essentially complete.** Live-tested and captured:
all report data schemas (Ledger, P&L `{Trades,Expenses}`, Detailed-P&L),
all file-delivery endpoints (PNL/Ledger/Tax PDF+Excel, contract-note list +
download, CML), auth-failure envelopes, session↔client binding, source-header
behaviour, `With_Exp` shape-switch, and the Freshdesk account structure +
ticket-field cascade. See `03_finx_api_reference.md`, `04_freshdesk_api_reference.md`.

**Resolved 2026-07-16 (this session):**
- ✅ **get-profile captured** — `mf.choiceindia.com/api/v2/investor/profile/
  extended` (JWT). Jini extracts **only the first name** from `FirstHolderName`;
  discards the heavy-PII rest (`03` §4.6b).
- ✅ **Font decided** — native system stack (mockups name no brand font; §8.1).
- ✅ **DB access** — assume the tunnel/prod connection works (owner: "just
  assume"); verify at implementation start.
- ✅ **MTF kept in scope** (owner: "keep it").

**All flow endpoints now captured (2026-07-16).** Remaining items are
confirmations/decisions, not blockers:
- **MTF `Margin` discriminator** — needs one capture from an MTF-holding
  account (`Margin:0`/`:1` identical on the no-MTF test account).
- **Holdings credential provenance** — the Holdings endpoint (`03` §4.6d) needs
  a FINX-issued JWT in the body (distinct from the SSO JWT); confirm where the
  backend obtains it.
- **Holding & Global Detail file delivery** — both have data endpoints but no
  captured PDF/download leg; decide data-card vs capture a file endpoint.
- Optional scope add: **Pay-in/Pay-out** (not in the 11 flows).

**⚠️ The FinX surface spans FIVE hosts + several auth schemes** — the
`FinXClient` interface must handle: `.NET` `/api/middleware` (SessionId
header+body), Go `/middleware-go` on `finx.` and on `api.` (SessionId, some
`Session `-prefixed, some unauth), MIS `/mis` (SSO JWT), `mf.` profile (SSO
JWT), and `finxomne. /COTI` (SessionId + `ssotoken` SSO-JWT header + FINX-JWT
in body). Not one wrapper — a per-backend adapter set.
- **MTF `Margin` discriminator** — kept in scope but still unverified
  (`Margin:0`/`:1` identical on a no-MTF account). Needs ONE capture of
  `GetLedgerDetailsPDF` from an account with live MTF holdings to confirm
  `Margin:1` is the discriminator. Until then the MTF flow can be built but its
  data path is unproven.

**Next build step**: the contracts-first OpenSpec change (below) — now writable
against real schemas instead of guesses.

### Build-readiness verdict (independent review, 2026-07-16)

**READY-WITH-CAVEATS** — OpenSpec proposals can start for well-specified
slices (RAG service, tracing, conversation store, widget shell, Tax flow,
FinX client interface). **Parallel fan-out is blocked** until a
**contracts-first change lands in main** containing (per CLAUDE.md rules):

1. **Widget ↔ backend wire contract** — the headline gap: no chat endpoint
   schema, no streaming decision, no render-block wire types (bubble / chip
   row / stepper card / file card / note-list / error bubble) exist anywhere.
2. Router I/O contract (Intent enum, `ExtractedParams`, `RouterResult`).
3. `FinXClient` interface + 3 envelope parsers + typed models + capture
   fixtures.
4. Flow/Step state-machine + guardrail config schema.
5. Conversation-store DB migration (single-owner task).
6. Remote-config schema (whats_new, limits, chips, greeting pool, products).
7. Tracing conventions (span taxonomy, `configure()` setup, `mask` signature).
8. Error taxonomy as shared config (§8.4).
9. LLM client wrapper (pinned model IDs + Haiku toggle).

Merge-conflict watch: the Intent enum, `FinXClient`, and remote-config schema
are files every flow task will want to touch — define ALL intents/methods/keys
up front and forbid flow tasks from editing them.

### Resolved 2026-07-16 (owner input)

- **Launch scope: full build (RAG + APIs)** — build the complete
  Phase-1-Live system; the test workbook's KB-only split is test sequencing,
  not build sequencing.
- **Flows without captured endpoints are BLOCKED, not stubbed** — Brokerage,
  Holding Statement, Global-Detail file delivery (and get-profile / Freshdesk
  field list) wait until their endpoints are captured. Launch proposals cover
  only flows with known endpoints: P&L, Ledger/MTF, Contract Note (list),
  Tax/CG, CML + RAG + tracing + store + widget.
- **Model IDs pinned**: `claude-sonnet-5` for router/RAG generation;
  `claude-haiku-4-5-20251001` as the configurable cheap-model toggle.
  Replaces the spec's non-existent "sonnet-4-6".
- **API verification phase before final contracts**: rather than deciding
  open API questions (Ledger one-call-vs-two, response envelopes, `Margin:1`
  MTF, CML response) on paper, the owner will scope **agents that test the
  live APIs** and capture real responses; the finalized contract docs get
  written from those captures. Until then, per-endpoint response contracts
  marked [GAP]/[CONFIRM] in `03_finx_api_reference.md` stay provisional.

- ~~Report APIs can't do PDF + email~~ → new `*PDF` endpoints captured:
  `GetGlobalPNLPDF`, `GetLedgerDetailsPDF`, `GetTaxReportPDF` variants, CML
  via `/mis/reports/generate`. Success schema for PNL PDF captured (URL /
  email confirmation string).
- ~~Which UI variants~~ → entry 1a, P&L flow 2a.
- `RequestFor`/`FileFormat` enums partially resolved via Android source:
  ViewType Mail=1/Download=2; FileFormatType Pdf=1/Excel=2 (but PNL PDF
  observed 0=download/1=email — per-endpoint semantics still to reconcile).
- `Margin` field discovered on `GetLedgerDetailsPDF` — likely the MTF
  discriminator (0 observed; confirm 1 = MTF).

### FinX API

1. **SessionId acquisition/lifetime/expiry undocumented** — no login/refresh
   endpoint anywhere. Biggest integration blocker. (Chatbot receives
   `sessionId`/`accessToken` via URL params from the app — confirm that
   suffices for all three backends.)
2. **Success schemas still missing**: Global PNL data (`GetGlobalPNLNew`),
   Detailed PNL data, Contract Notes success `Body`, CML response, Ledger
   PDF response.
3. **"11 reports" ≠ documented endpoints** — authoritative 11-item list and
   per-flow endpoint mapping needed (agent reconciliation in progress).
4. **Undocumented endpoints blocking their flows**: get-profile, Brokerage,
   Holding Statement, Contract Note per-note download (by `file_id`), Global
   Detail download, Freshdesk raise-ticket (field list "to be shared").
5. **Three backends, three conventions**: `/api/middleware` (PascalCase,
   SessionId header+body), `/middleware-go` (snake_case, header only),
   `/mis` (JWT + `authType: jwt` + `source`). One client wrapper won't fit.
6. `RequestFor` semantics differ per endpoint (0/1 on PNL PDF vs 1/2 enum vs
   2 on Tax) — reconcile before coding the flow engine.
7. Tax/PNL report URLs unauthenticated once created — server-side fetch +
   discard enforced; confirm which other report URLs share this.
7b. **Ledger delivery: one call or two?** The flow spec describes a two-step
   (data API → download API); `GetLedgerDetailsPDF` generates the file in one
   call and likely supersedes it. **Owner decision: defer — resolve during
   the API verification phase** (agents test the live APIs, capture real
   responses, then the contract is finalized).

### Product / architecture

8. **"Phase 1" overloaded** (build vs personalization tier vs test-plan
   phasing); UI mockups assume APIs present while the Phase-1 test sheet is
   KB-only — align launch sequencing.
9. **Model ID "sonnet-4-6" is not real** — pin the actual Claude model ID
   (+ Haiku toggle target).
10. **Conversation-store schema undefined** — explicit design task (§3.2).
11. **10-message cap behavior** for a legitimate second query — soft
    "conversation number" guardrail proposed, undecided.
12. In-spec open tags: CML/Global-Detail PDF password status [ASSUMPTION];
    client with no registered email (EC-9 [OPEN]); contract-note publish time
    for "today's note" (EC-3 [OPEN]); widget-killed-mid-generation resume
    [ASSUMPTION].

### RAG / eval / tracing

13. **Top-K unspecified**; FTS half of "hybrid" (tsvector + fusion/RRF)
    undefined; **reranker unchosen** (or explicitly skipped).
14. **Sequential scan vs Matryoshka** for the 3072-dim KB — confirm
    sequential scan as the explicit Phase-1 decision.
15. **No pass/fail thresholds mandated** — pick per-metric thresholds
    (tutorial default 0.7/0.8); choose the DeepEval judge LLM (cost/quality).
16. **PII masking policy** for traces — which fields, before any export.
17. **No machine-runnable Golden test set** — author ≥20
    `ConversationalGolden`s; spreadsheet README counts (36/46) don't match
    actual sheet counts (41/47).
18. **Remote-config surface assumed but unspecified** — no config schema for
    What's New / limits / chips / product list (C1 hallucination-bounds list
    is a Phase-2 to-do).
19. Design tokens/fonts pending from FinX team.
