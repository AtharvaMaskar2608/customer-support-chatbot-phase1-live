# Proposal: tracing-observability

## Why

`02_technical_spec.md` §6 and §3.3 mandate DeepEval `@observe` tracing across the pipeline:
typed spans (agent/retriever/llm/tool), thread stitching by `thread_id`, **mandatory PII
masking** (names, emails, Client IDs, ledger amounts) via `mask=` in `trace_manager.configure`,
and a strict production rule — never run local LLM-judge metrics in prod. Contracts-foundation
freezes the *conventions* (span taxonomy, the `trace_manager.configure()` setup contract, the
`mask` function signature); this change is their **implementation** in `app/tracing/`, so every
other package (orchestrator agent span, RAG retriever/llm spans, engine/flow tool spans) has one
consistent wiring to import rather than each re-deriving decorator usage and re-implementing PII
redaction.

## What Changes

- **Global setup wrapper** — `configure_tracing(environment, sampling_rate=None,
  confident_api_key=None)` wrapping `trace_manager.configure(...)`: environment-derived defaults
  (`sampling_rate=1.0` in development, a lower config-driven rate in production per §6.2), always
  passes `mask=mask_pii`, tags `environment`, and wires the LLM client for auto-patching. Called
  once from the orchestrator's FastAPI lifespan (this change exposes the function; it does not
  edit `app/main.py`).
- **PII mask implementation** — `mask_pii(data)` conforming to the frozen `mask` signature,
  recursing dicts/lists/strings and redacting the concrete field list below before any span
  input/output leaves the process.
- **Typed span ergonomics + thread stitching** — thin re-exports/partials so every change types
  its spans identically: `agent_span`/`retriever_span`/`llm_span`/`tool_span` (=
  `observe(type=...)`), plus `stitch_thread(thread_id, user_id, *, turn_number, model_version)`
  wrapping `update_current_trace(thread_id=..., user_id=..., metadata={...}, tags=[...])` for the
  §6.4 multi-turn stitch, and a re-export of `update_current_span` (for `retrieval_context` on
  retriever spans).
- **Anthropic auto-patch caveat — both paths implemented (§6.2)** — a capability probe
  determines whether the installed DeepEval `configure()` exposes an Anthropic hook.
  **Path A (auto):** if supported, pass the pinned Claude client to `trace_manager.configure`
  and let it intercept `messages.create` (model + token usage captured automatically).
  **Path B (manual):** if the documented signature only exposes `openai_client=` (the caveat),
  fall back to manual `llm`-span logging — `log_llm_span(response, model)` reads the Anthropic
  response `usage` (`input_tokens`/`output_tokens`) onto the current `llm` span via
  `update_llm_span()`/`update_current_span()`. The active path is logged at startup so it is
  never ambiguous which one is live.
- **Housekeeping** — `clear_traces()` housekeeping for the long-running server (bound in-memory
  trace growth when not exporting to Confident AI) exposed as `maybe_clear_traces()`; document
  `CONFIDENT_TRACE_FLUSH=1` for short-lived eval scripts (not the server).
- **Production guard** — a helper that refuses to attach local `metrics=[...]` LLM judges when
  `environment == "production"` (§6.5); prod uses async `metric_collection=` only.

## Capabilities

### New Capabilities

- `tracing-observability`: the concrete DeepEval wiring — `configure_tracing`, `mask_pii`, the
  typed-span helpers + `stitch_thread`, the dual Anthropic auto-patch/manual llm-span path, trace
  housekeeping, and the prod no-local-judge guard.

### Modified Capabilities

- `tracing-conventions` (contracts-foundation): **consumed, not modified** — this change
  *implements* the frozen span taxonomy, `configure()` contract, and `mask` signature; it does
  not change any of those signatures.

## Impact

- **New code**: `app/tracing/**` (setup wrapper, `mask_pii`, span helpers, dual llm-span path,
  housekeeping, prod guard).
- **APIs**: internal only — decorators/helpers imported by other packages; no HTTP surface, no
  FinX/Freshdesk contact.
- **Downstream/dependencies**: depends on contracts-foundation (#0); consumed by orchestrator
  (#5, root `agent` span + `configure_tracing` + `stitch_thread`), rag (#4, retriever/llm spans),
  flow-engine/flows (#2/#6–11, `tool` spans). Each of those applies the decorators to its own
  functions — this change only supplies the wiring.
- **Out of scope**: no metric definitions/thresholds and no `ConversationSimulator` (that's
  eval-harness #16); no Confident AI account setup; no per-function decoration of other packages'
  code.

## Files touched

Exclusive to this change (map row 14) — nothing outside it:

- `app/tracing/**` — new package (`configure_tracing`, `mask_pii`, span helpers,
  `stitch_thread`, `log_llm_span`, housekeeping, prod guard).
- `tests/tracing/**` — unit tests (mask coverage, both auto-patch paths, prod-guard behavior).

Untouched: `app/config/*` and any `tracing-conventions` contract file in `app/contracts/*`
(owned by contracts-foundation — imported, not edited), `app/llm/client.py`, `pyproject.toml`/
lockfile, migrations, root config, `app/main.py` (orchestrator wires the startup call).

## Contracts & API structure

Signatures below conform to the frozen `tracing-conventions` capability; where the contract
constrains a signature it is imported, not redefined.

- `configure_tracing(environment: Literal["development","staging","production"],
  sampling_rate: float | None = None, confident_api_key: str | None = None) -> None` — wraps
  `trace_manager.configure(...)`; defaults `sampling_rate` to `1.0` in development and the
  config value (lower) in production; always sets `mask=mask_pii` and `environment=`; selects
  the Anthropic auto-patch path (A/B) and logs which is active. Idempotent (safe to call once at
  startup).
- `mask_pii(data: Any) -> Any` — the frozen `mask` hook. Recurses `dict`/`list`/`str`. Concrete
  redaction list:
  - **Emails** → `[EMAIL_REDACTED]` (regex; covers already-masked `san***.harsha@gmail.com`).
  - **Client IDs** → `[CLIENT_ID]` (FinX code pattern, e.g. `X008593` — `^[A-Za-z]\d{5,6}$`).
  - **PAN** → `[PAN]` (`[A-Z]{5}\d{4}[A-Z]`; PAN is the PDF password, must never trace).
  - **Ledger / currency amounts** → `[AMOUNT]` (₹/number-with-decimals patterns).
  - **Phone numbers** → `[PHONE]` (10-digit / +91).
  - **Names** → masked by **structured field key** (`name`, `client_name`, `full_name`, etc.),
    not free-text NER (unreliable). `[CONFIRM]`: names in free text are best-effort only;
    recommendation is that get-profile name fields are never placed in span payloads in the first
    place. Field-list is proposed here and open to owner tightening (§9 "policy undecided").
- Typed span helpers: `agent_span = observe(type="agent")`, `retriever_span`, `llm_span`,
  `tool_span`; re-export `observe`, `update_current_span`, `update_current_trace`.
- `stitch_thread(thread_id: str, user_id: str, *, turn_number: int, model_version: str) -> None`
  — `update_current_trace(thread_id=..., user_id=..., metadata={"turn_number","model_version"},
  tags=[...])` for §6.4 multi-turn stitching.
- `log_llm_span(response, model: str) -> None` — manual **Path B**: pushes model + `usage`
  token counts onto the current `llm` span when auto-patch is unavailable.
- `maybe_clear_traces() -> None` — periodic `trace_manager.clear_traces()` for the long-running
  server.
- `assert_no_local_metrics(environment)` / a `metrics` guard — refuses local LLM-judge metrics in
  production (§6.5).

## Dependencies & contracts consumed

- **Frozen contracts imported**: `tracing-conventions` (span taxonomy, `configure()` setup
  contract, `mask` signature), `llm-client` (the pinned Claude client to auto-patch or
  instrument), environment/sampling/`confident_api_key` config from `app/config`. `deepeval` is
  declared in contracts-foundation's `pyproject.toml`.
- **Must land first**: contracts-foundation (#0).
- **Parallel-safe**: all consumers (#2, #4, #5, #6–11) — this change ships the wiring; they apply
  the decorators to their own functions independently. The orchestrator (#5) is the sole caller of
  `configure_tracing` from `app/main.py`.

## Done condition & test command

Done when: `configure_tracing` sets `sampling_rate=1.0` in dev / the lower config rate in prod,
always installs `mask_pii`, and resolves + logs the live Anthropic path (A or B); `mask_pii`
redacts every listed PII class in nested inputs/outputs and leaves non-PII intact; `stitch_thread`
sets `thread_id`/`user_id`/metadata on the current trace; the manual `log_llm_span` path records
model + token usage when auto-patch is absent; the prod guard blocks local metrics when
`environment=="production"`; `maybe_clear_traces()` clears buffered traces.

`pytest tests/tracing/` green — offline, **no Confident AI connection and no real LLM call**
(both auto-patch paths exercised via a stubbed DeepEval `configure`).
