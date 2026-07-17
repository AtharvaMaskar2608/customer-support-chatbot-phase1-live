# Loop state: flow-engine-runtime

Worktree: /home/choice/projects/customer-support/flow-engine-runtime
Branch: flow-engine-runtime (from main @ cfb22a1 — contracts-foundation merged)
testCommand: `pytest tests/engine/`
Baseline: `uv run pytest` = 82 passed (before any engine code).

## Key design decisions (contract-derived)
- **Byte-fetch seam (blessed split):** `fetch_report_bytes` + `FinX*Error` live in
  `finx-http-adapters` (`app/finx/adapters/`, not yet on main). Engine consumes via
  an injected `ByteFetcher` port + a guarded import in `app/engine/faults.py`
  (`except ModuleNotFoundError` → local placeholder exceptions). Engine catches the
  SPECIFIC fault types, never a shared base, so it is agnostic to the adapters'
  hierarchy. Wave 2 = drop-in, no engine edit. [SEAM]
- **FlowDefinition:** the frozen `FlowSpec` (intent/config/steps) is the minimal
  discovery contract; the engine defines a richer `FlowDefinition` Protocol
  (step_title/step_chips/report_title/password_hint/supports_email/generate) that
  the six downstream flow changes implement. Engine defines it because flows
  depend on the engine.
- **EngineContext vs frozen SessionContext:** `SessionContext` is frozen and holds
  no runtime deps, so the engine wraps it in an `EngineContext` carrying the
  byte_fetcher, cache, clock, and follow-up count/cap. `advance(..., *, ctx)` types
  `ctx` as `EngineContext` (proposal signatures are "indicative"). [DEVIATION-noted]
- **deliver -> list[RenderBlock]:** the proposal's `-> RenderBlock` is indicative;
  EC-12 (text + chips) and file-card-plus-follow-up need >1 frozen block, so
  delivery returns an ordered list. [DEVIATION-noted]
- **E-FETCH copy under D1 non-streaming:** retry runs server-side within the turn;
  the surfaced E-FETCH bubble carries the verbatim `second_line` copy. The
  first-line reassurance is not emitted as a separate block (nothing to stream in
  a one-response-per-turn design). [DEVIATION-noted]
- **Email mask rule:** keep first 3 local-part chars, `***`, keep from the first
  `.` onward, keep domain, lowercased. `sanjay.harsha@…` → `san***.harsha@…`;
  `sanjayharsha@…` → `san***@…`. [DERIVED]
- **Nudge copy** for the defensive out-of-range reject is engine-default + flow
  override (no frozen copy exists). Calendars hard-disable out-of-range so this is
  belt-and-suspenders. [CONFIRM — final nudge copy is a flow concern]

## Tasks
- [x] tasks.md + loop.md authored and committed
- [x] T1 scaffolding + fault seam + ports (faults/ports/events/results/__init__;
      test_faults.py 3 passed; `import app.engine` OK with adapters absent)
- [x] T2 step progression + stepper-edit (steps.py: next_step/reopen_step/
      materialize_steps/build_stepper_card + conftest fakes; test_steps.py 6 passed)
- [x] T3 calendar + date-window (calendar.py: build_calendar hard-disable via
      bounds, validate_range exact leap-safe clamp, out_of_range_nudge;
      test_calendar.py 9 passed)
- [x] T4 FY resolution (fy.py: resolve_fy via frozen helpers, normalize_fy,
      out-of-window -> EYearError with no adapter call; test_fy.py 6 passed)
- [x] T5 follow-up cap (chips.py shared factories + followups.py enforce_followups
      cap-from-ctx; test_followups.py 3 passed)
- [x] T6 selection/byte cache (cache.py SelectionCache: frozen-key, 900s TTL,
      evict-on-expiry, no cross-contamination; resend-bypass enforced in delivery;
      test_cache.py 4 passed)
- [x] T7 error mapping (errors.py map_error: verbatim frozen copy + chips, {FY_short}/
      {defaultFY}/{list} substitution, E-YEAR dynamic FY chips, E-FETCH second_line,
      no Reason/URL/HTTP leak; test_errors.py 6 passed)
- [x] T8 delivery assembly (delivery.py deliver: generate+cache+fetch+retry-once,
      E-FETCH/E-TIMEOUT/E-NODATA/E-UNKNOWN, file-card rename+CML exception+password,
      mask_email, EC-12, resend bypass; test_delivery.py 14 passed)
- [x] T9 discovery registry (registry.py discover+FlowRegistry; app/flows/__init__.py
      generic lazy discovery + register/get_flow; test_registry.py 3 passed)
- [x] T10 executor + public API (executor.py advance: full dispatch/progression/
      generation gating; __init__ re-exports 40-name public surface;
      test_executor.py 7 passed; full engine suite 61 passed)
- [x] T11 suite green + doneCondition (testCommand `pytest tests/engine/` = 61 passed;
      full `uv run pytest` = 143 passed; no frozen surface touched)

Current task: verifier panel (round 1).

## doneCondition audit (each clause → covering test)
1. advance drives first-step→generation→delivery → test_executor::test_drives_full_flow_first_step_to_delivery
2. stepper-edit clears downstream, no refetch until generation → test_executor::test_stepper_edit_clears_downstream_and_refetches_nothing
3. ≤2 follow-up cap escalates on the 3rd → test_executor::test_third_followup_escalates + test_followups
4. calendars hard-disable out-of-range → test_calendar (bounds) + test_executor::test_out_of_range_date_is_nudged_not_progressed
5. out-of-window FY → E-YEAR, no adapter call → test_executor::test_fy_out_of_window_yields_e_year_with_no_adapter_call + test_fy
6. FinXFetchError → exactly one silent retry then E-FETCH → test_delivery::test_fetch_error_triggers_exactly_one_silent_retry_then_succeeds + ::test_second_fetch_error_surfaces_e_fetch
7. 15-min cache hit within TTL; resend bypasses → test_cache + test_delivery::test_cache_hit_skips_generate_and_fetch + ::test_resend_bypasses_cache
8. rename display filename (CML excepted) + mask email → test_delivery::test_url_delivery_builds_renamed_file_card + ::test_cml_keeps_server_filename + ::test_email_confirmation_masks_registered_email
9. error mapping verbatim §8.4 copy → test_errors (all codes)
10. registry discovers a test FLOW with no __init__ edit → test_registry::test_discovers_module_level_flow_without_editing_init
11. fake adapters + frozen fixtures, zero network/LLM → whole suite uses FakeByteFetcher; no httpx/anthropic/openai calls

## Verifier rounds
### Round 1 (3 fresh panels: spec-compliance / edge-cases / contract-surface)
Result: NO blocking divergences. All findings minor/uncertain; several traced by
the verifiers themselves to spec gaps (copy change-0 never froze) or the proposal's
explicit parallel-build allowance. Triage:
- FIX (actionable): engine hardcoded the silent-retry count → consume frozen
  `ByteValidation.silent_retries` (contract#1, edge#4). ADDRESSED (round-2 change).
- FIX (actionable): out-of-range reject should use "the flow's nudge copy" →
  declare `range_nudge` on the FlowDefinition contract (spec#2/edge#1). ADDRESSED.
- KEEP (indicative signatures — proposal says "indicative"; frozen SessionContext
  is dep-free): `advance/deliver/map_error/enforce_followups` ctx/return shapes.
- KEEP (proposal-blessed parallel build): engine consumes an injected `ByteFetcher`
  rather than importing `fetch_report_bytes`; Wave-2 wiring injects the real one.
- KEEP (engine must NOT reimplement magic-byte checks — proposal explicit): the
  ReportBytes path does not re-validate; the adapter validates raw bytes.
- KEEP (frozen-types split): follow-up counter lives in the orchestrator's
  ConversationContext.follow_up_count (FlowState has no counter); engine enforces.
- CARRY [SPEC-SUSPECT]: frozen E-NODATA copy is FY-worded ("for FY {FY_short}") but
  E-NODATA is shared with date-range flows — awkward for ledger/contract-notes.
  Flag to team lead; do NOT reinterpret. [see carried items]
- CARRY [SPEC-TENSION]: frozen E-FETCH `text` (first line "during retry") is never
  surfaced under D1 non-streaming; proposal says the surfaced bubble is the verbatim
  second line. Following the proposal. [see carried items]

### Round 2 (3 fresh panels, post round-1 fixes)
Result: round-1 fixes confirmed good (silent_retries config-driven; retry counters
correct at 0/1/2). No blocking divergences. Two NEW actionable findings fixed:
- FIX: typed FinX faults RAISED by the adapter binding (during generation, or a
  401/5xx on the report-URL GET) escaped `deliver` uncaught — the proposal's
  "FinXTimeoutError ⇒ E-TIMEOUT / any other non-success ⇒ E-UNKNOWN" was
  unreachable from the delivery path. ADDED `_safe_generate` + broadened the fetch
  catch to FinXAuthError/FinXTransportError → all typed faults now map to the
  taxonomy (delivery.py). Tests: generation-raised timeout/auth/transport + fetch
  auth/transport → E-TIMEOUT/E-UNKNOWN.
- FIX: a `StepKind.confirm` step could never be completed (no event marked it done)
  → any flow with the AY→FY confirm step would stall. ADDED a `Confirm` event +
  `_handle_confirm` in the executor. Test: [fy, confirm, generate] progresses on
  Confirm.
- KEEP/CARRY: remaining items are the same indicative-signature / no-frozen-copy /
  spec-tension items from round 1 (unchanged stance). EC-12 fires on any partial
  (frozen copy is direction-specific — emitted verbatim as required).

## Open questions / carried items
- [SEAM] finx-http-adapters must re-export `FinXFetchError`/`FinXTimeoutError`/
  `FinXAuthError`/`FinXTransportError` at `app.finx.adapters` top level (engine
  imports them there in Wave 2). Flag to team lead for cross-change coordination.
- [CONFIRM] final calendar out-of-range nudge copy (now a declared optional
  `range_nudge` on the FlowDefinition contract; engine default until flows set it).
- [SPEC-SUSPECT] frozen E-NODATA copy is FY-worded but applied to all no-data flows
  (incl. date-range ledger/contract-notes). Not reinterpreted; raised to team lead.
- [SPEC-TENSION] frozen E-FETCH first-line `text` vs proposal's "silent" retry under
  D1 non-streaming: engine surfaces the verbatim second line only.

## Escalations
- Raised to team lead: (1) [SEAM] adapters re-export of FinX fault types; (2)
  [SPEC-SUSPECT] E-NODATA FY-worded copy shared with date-range flows. Neither
  blocks shipping this change.
