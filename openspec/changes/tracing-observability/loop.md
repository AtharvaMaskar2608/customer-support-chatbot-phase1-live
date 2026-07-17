# loop.md — tracing-observability

Worktree lead loop state. If it isn't here, it didn't happen.

- Change ID: tracing-observability
- Branch/worktree: /home/choice/projects/customer-support/tracing-observability
- Base at fan-out: main @ cfb22a1
- testCommand: `pytest tests/tracing/`
- doneCondition: see manifest.yaml
- Owner speed directive: PR target ~35 min; FAST VERIFY (1 panel, 2-round cap).

## Frozen surface confirmed (do NOT edit)

- `app/contracts/tracing.py` — SpanType taxonomy, `TraceManager.configure` contract,
  `MaskFn` signature, `PII_KEYS`, `default_mask`, `inline_judge_allowed`,
  `new_thread_id`. Imported, never edited.
- `app/llm/client.py`, `app/config/**`, `app/main.py`, `app/contracts/**`,
  `app/finx/*.py`, `app/store/migrations/**`, `pyproject.toml`, `uv.lock`.

## Environment findings (load-bearing)

- Installed DeepEval = **4.1.1**. Real `trace_manager.configure(...)` **exposes
  `anthropic_client=`** → the LIVE path is **Path A (auto-patch)**. Path B (manual
  llm-span) still implemented + tested for older DeepEval via a stubbed configure.
- Real `configure` stores: `trace_manager.environment`, `.sampling_rate`,
  `.custom_mask_fn` (our mask), `.confident_api_key`. `mask` attr is a bound method.
- Offline (no key): `get_all_traces_dict()` returns `[]` even after running observed
  fns (traces retained only when exporting/evaluating). So `maybe_clear_traces` is
  spec-tested via a spy on `trace_manager.clear_traces`, not by trace counts.
- Real API names wrapped: `observe(_func=None,*,metrics,metric_collection,type,...)`,
  `update_current_span(...,retrieval_context,metadata,...)`,
  `update_current_trace(...,thread_id,user_id,tags,metadata,turn_id,...)`,
  `update_llm_span(model,input_token_count,output_token_count,...)`,
  `trace_manager.clear_traces()`.

## Design decisions (from proposal, recorded so a fresh agent can resume)

- `configure_tracing` takes an optional keyword-only `anthropic_client=None` — a
  backward-compatible superset of the documented 3-arg contract, needed so the
  orchestrator can pass the pinned client for Path A auto-patch ("wires the LLM
  client for auto-patching"). Documented positional contract unchanged.
- `mask_pii` reuses frozen `PII_KEYS` (substring, case-insensitive) for key-based
  redaction → `***` (matches frozen `default_mask` precedent); adds value-level regex
  for the 5 string-embedded PII classes with the proposal's tokens.
- Prod sampling default = 0.1 module constant (no config field exists; frozen config
  has none). Caller may override via `sampling_rate=`.
- `assert_no_local_metrics` reuses frozen `inline_judge_allowed`.

## Progress

- Tasks completed: 1.1, 1.2 (scaffold + tasks.md + loop.md).
- Current task: 2.x mask_pii.
- Verifier rounds run: 0.
- Findings per round: n/a.
- Open questions: none blocking. `[CONFIRM]` names-in-free-text are best-effort
  (proposal § contracts, owner may tighten); Client-ID value regex is anchored
  (`^...$`) per the proposal, so embedded client ids inside sentences are not
  value-redacted (they are still key-redacted under any pii key).

## Metrics (filled at completion)

- Verifier rounds used: TBD
- Findings per round: TBD
- Escalations: TBD
- Harness runs: TBD
