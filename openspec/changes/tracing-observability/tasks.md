# Tasks: tracing-observability

Implementation of the frozen `tracing-conventions` contract in a new `app/tracing/`
package. Every task is written from `proposal.md`; tests assert what the proposal
promised, not what the code happens to do.

## 1. Scaffold

- [x] 1.1 Create `app/tracing/` package and `tests/tracing/` package.
- [x] 1.2 Author `tasks.md` and `loop.md` (this file + loop state). First commit.

## 2. PII mask (`app/tracing/mask.py`)

- [x] 2.1 `mask_pii(data: Any) -> Any` conforming to the frozen `MaskFn` signature.
      Recurses `dict`/`list`/`str`. Reuses the frozen `PII_KEYS` for key-based
      redaction (names + credentials + amounts by key).
- [x] 2.2 Value-level regex redaction on strings, per the proposal's concrete list:
      emails → `[EMAIL_REDACTED]` (covers already-masked `san***.harsha@gmail.com`),
      Client IDs → `[CLIENT_ID]` (`^[A-Za-z]\d{5,6}$`), PAN → `[PAN]`
      (`[A-Z]{5}\d{4}[A-Z]`), ledger/currency amounts → `[AMOUNT]` (₹/decimal),
      phone numbers → `[PHONE]` (10-digit / +91).
- [x] 2.3 Tests: every PII class redacted in nested inputs/outputs; non-PII intact.

## 3. Span helpers + thread stitching + manual llm-span (`app/tracing/spans.py`)

- [x] 3.1 Typed span helpers `agent_span`/`retriever_span`/`llm_span`/`tool_span`
      (= `observe(type=...)`); re-export `observe`, `update_current_span`,
      `update_current_trace`.
- [x] 3.2 `stitch_thread(thread_id, user_id, *, turn_number, model_version)` wrapping
      `update_current_trace(...)` for the §6.4 multi-turn stitch.
- [x] 3.3 `log_llm_span(response, model)` — manual Path B: reads the Anthropic
      response `usage` (`input_tokens`/`output_tokens`) onto the current `llm` span
      via `update_llm_span()`.
- [x] 3.4 Tests: helpers carry the right `type`; stitch_thread sets
      thread_id/user_id/metadata; log_llm_span forwards model + token counts.

## 4. Setup wrapper + prod guard + housekeeping (`app/tracing/setup.py`)

- [x] 4.1 `configure_tracing(environment, sampling_rate=None, confident_api_key=None)`
      wrapping `trace_manager.configure(...)`: sampling defaults (1.0 dev / lower in
      prod), always `mask=mask_pii`, tags `environment`, Anthropic path A/B probe,
      logs the live path. Idempotent.
- [x] 4.2 Anthropic auto-patch probe: Path A (configure accepts `anthropic_client`) →
      forward the pinned client; Path B (only `openai_client`) → fall back to manual
      `log_llm_span`. Log which is active.
- [x] 4.3 `maybe_clear_traces()` — periodic `trace_manager.clear_traces()` for the
      long-running server (only when not exporting to Confident AI).
- [x] 4.4 `assert_no_local_metrics(environment, metrics=None)` — refuses local
      LLM-judge `metrics=[...]` in production (§6.5); reuses frozen
      `inline_judge_allowed`.
- [x] 4.5 Tests: both paths exercised via a stubbed DeepEval `configure`; prod guard
      raises; sampling defaults per environment; maybe_clear_traces clears.

## 5. Public API + gates

- [x] 5.1 `app/tracing/__init__.py` re-exports the public surface.
- [x] 5.2 `pytest tests/tracing/` green; doneCondition passes; offline (no Confident
      AI connection, no real LLM call).

## 6. Verify + ship

- [x] 6.1 Fresh spec-verifier panel (3 lenses). Fix divergences; re-panel if blocking.
- [x] 6.2 Rebase onto latest origin/main; full `uv run pytest` green; push; open PR.
