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
- [ ] T10 executor + public API
- [ ] T11 suite green + doneCondition

Current task: T10.

## Verifier rounds
(none yet)

## Open questions / carried items
- [SEAM] finx-http-adapters must re-export `FinXFetchError`/`FinXTimeoutError`/
  `FinXAuthError`/`FinXTransportError` at `app.finx.adapters` top level (engine
  imports them there in Wave 2). Flag to team lead for cross-change coordination.
- [CONFIRM] final calendar out-of-range nudge copy (flow-owned).

## Escalations
(none)
