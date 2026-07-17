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
- [ ] T2 step progression + stepper-edit
- [ ] T3 calendar + date-window
- [ ] T4 FY resolution
- [ ] T5 follow-up cap
- [ ] T6 selection/byte cache
- [ ] T7 error mapping
- [ ] T8 delivery assembly
- [ ] T9 discovery registry
- [ ] T10 executor + public API
- [ ] T11 suite green + doneCondition

Current task: T2.

## Verifier rounds
(none yet)

## Open questions / carried items
- [SEAM] finx-http-adapters must re-export `FinXFetchError`/`FinXTimeoutError`/
  `FinXAuthError`/`FinXTransportError` at `app.finx.adapters` top level (engine
  imports them there in Wave 2). Flag to team lead for cross-change coordination.
- [CONFIRM] final calendar out-of-range nudge copy (flow-owned).

## Escalations
(none)
