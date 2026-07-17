# Tasks: flow-engine-runtime

Decomposed from `proposal.md` + `specs/` (the contract). Ordered so each task
builds on the last; tests are written FROM THE PROPOSAL, not the implementation.
Every task commits code + its tests + a `loop.md` update in one commit.

Owned files only: `app/engine/**`, `app/flows/__init__.py`, `tests/engine/**`
(plus this `tasks.md` / `loop.md`). Frozen surfaces are imported read-only.

Integration seam (blessed split, Wave 1 parallel build): the byte-fetch primitive
`fetch_report_bytes(url, *, expected_format) -> bytes` and the typed exceptions
`FinXFetchError` / `FinXTimeoutError` / `FinXAuthError` / `FinXTransportError`
are OWNED by `finx-http-adapters` (`app/finx/adapters/`), not yet on main. The
engine consumes them through an injected `ByteFetcher` port and a guarded import
seam (`app/engine/faults.py`) that falls back to local placeholder exception
classes ONLY while `app.finx.adapters` is absent. Wave 2 drops in the real module
with no engine edit. The engine catches the specific fault types (never a shared
base) so it is agnostic to the adapters' exception hierarchy.

---

## T1 — Engine scaffolding, fault seam, and flow/deps ports
Create `app/engine/{__init__.py,faults.py,ports.py,events.py,results.py}`.
- `faults.py`: guarded `from app.finx.adapters import FinX*Error` on
  `ModuleNotFoundError` → local placeholder classes matching the blessed names.
- `ports.py`: `ByteFetcher` Protocol (matches `fetch_report_bytes` signature);
  `FlowDefinition` Protocol (extends frozen `FlowSpec` with the engine-facing
  delivery/presentation surface: `step_title`, `step_chips`, `report_title`,
  `password_hint`, `supports_email`, `generate`); `GenerationResult` union
  (URL / raw-bytes / email-confirmation / in-band no-data / in-band error);
  `EngineContext` (wraps frozen `SessionContext` + injected `byte_fetcher`,
  `cache`, `clock`, follow-up count + cap).
- `events.py`: `FlowEvent` union (`ParamSelected`, `DateSelected`, `Resend`,
  `ReopenStep`, `FollowUp`).
- `results.py`: `FlowStepResult`, `Escalation`, FY-resolution + delivery result types.
**Done:** `uv run python -c "import app.engine"` exits 0 with `app.finx.adapters`
absent; the guarded seam uses `ModuleNotFoundError` (not blanket `ImportError`).

## T2 — Step progression + stepper-edit semantics
`app/engine/steps.py`: `next_step(state, flow) -> Step | None`;
`reopen_step(state, step_id) -> FlowState`; stepper-card build from flow steps;
pre-fill steps already satisfied by router `ExtractedParams`.
**Done:** `next_step` returns the first incomplete step and `None` when all done;
pre-filled steps are marked done and skipped; `reopen_step` sets the target step
active and CLEARS all downstream selections while leaving upstream intact; the
built `StepperCard` marks done steps tappable. Tests: `tests/engine/test_steps.py`.

## T3 — Calendar + per-flow date-window enforcement
`app/engine/calendar.py`: `build_calendar(flow, today) -> Calendar`;
`validate_range(flow, from_, to) -> bool` (+ nudge). Reads each flow's frozen
`DateWindow` (floor, `cap_relative_days`, `max_range_years`) — windows are NOT
unified. `add_years` helper handles Feb-29. Out-of-range dates hard-disabled in
the calendar (never validate-after); the defensive reject path returns invalid.
**Done:** floors/caps differ per flow and are honored; `max_range_years` clamp is
exact across a leap boundary; an out-of-range selection is rejected. Tests:
`tests/engine/test_calendar.py`.

## T4 — Financial-year resolution
`app/engine/fy.py`: `resolve_fy(params, today) -> FYResolved | EYearError` using
the FROZEN FY helpers from `app.contracts.flow` (imported, never reimplemented —
no FY date math in `app/engine/`). Out-of-window FY → `EYearError` BEFORE any
generation call; AY→FY confirmation surfaced; three in-window FY chips computed
from `supported_fys`.
**Done:** in-window FY resolves to the long form; an out-of-window FY yields
`EYearError` and triggers NO adapter/generate call; a far-future `today` resolves
correctly (three years never hardcoded). Tests: `tests/engine/test_fy.py`.

## T5 — ≤2 follow-up cap + escalation
`app/engine/followups.py`: `enforce_followups(ctx) -> Escalation | None`. The
engine enforces the cap (`Limits.follow_up_cap`, default 2) and the escalation
transition; the router decides whether a turn is a follow-up.
**Done:** the 1st and 2nd unresolved follow-ups pass; the 3rd returns an
`Escalation` carrying raise-ticket + call-support chips and stops asking. Tests:
`tests/engine/test_followups.py`.

## T6 — Per-flow 15-minute selection/byte cache
`app/engine/cache.py`: `SelectionCache` keyed by the frozen
`selection_cache_key(intent, params)`; TTL 900s (`CacheConfig`); session-scoped;
`resend` bypasses; edits change the key so no cross-contamination.
**Done:** a hit within TTL returns cached bytes; expiry misses; `resend` bypasses;
two different selections yield different keys. Tests: `tests/engine/test_cache.py`.

## T7 — Error-taxonomy mapping
`app/engine/errors.py`: `map_error(exc_or_result, flow, *, ctx) -> ErrorBubble`
mapping typed adapter exceptions AND in-band business results to
`E-NODATA/E-YEAR/E-TIMEOUT/E-FETCH/E-UNKNOWN` with VERBATIM copy + recovery chips
from the frozen `error-taxonomy` (`app/contracts/errors.py`). Placeholder
substitution ({FY_short},{defaultFY},{list},{masked_email}); E-YEAR renders the 3
dynamic FY chips; E-FETCH surfaces the verbatim second-line copy; no Reason / HTTP
code / URL ever appears in copy.
**Done:** each code emits its exact frozen copy + chip labels; placeholders
substituted; E-YEAR chips are the 3 in-window FYs. Tests: `tests/engine/test_errors.py`.

## T8 — Delivery assembly
`app/engine/delivery.py`: `deliver(flow, params, ctx) -> list[RenderBlock]`.
generate → cache lookup (unless resend) → `fetch_report_bytes` → ONE silent retry
on `FinXFetchError` (fresh generation → fresh URL → refetch) → second failure
`E-FETCH`; `FinXTimeoutError` → `E-TIMEOUT` (selections preserved); in-band
no-data → `E-NODATA`; other non-success → `E-UNKNOWN`. Builds the file-card
(renamed display filename; CML keeps `Client_Master_List.pdf`; password hint;
helper copy) or the email-confirmation bubble (masked registered email); EC-12
partial dual-format email failure. Stores fetched bytes in the cache.
**Done:** URL delivery fetches once and renames (CML excepted); one FinXFetchError
→ exactly one silent retry → E-FETCH; FinXTimeoutError → E-TIMEOUT; no-data →
E-NODATA; a cache hit skips the fetch; `resend` bypasses the cache; email is
masked (`san***.harsha@gmail.com`); EC-12 emitted on partial email failure.
Tests: `tests/engine/test_delivery.py`.

## T9 — Discovery registry (no per-flow edit)
`app/engine/registry.py` (reusable discovery) + `app/flows/__init__.py`
(discovery + `register` + `get_flow`, generic — NO per-flow imports). Scans the
flow package via `pkgutil` for module-level `FLOW` (per frozen `FLOW_ATTR`), keys
by `Intent`.
**Done:** a test `FLOW` module is discovered and registered by intent with NO edit
to `app/flows/__init__.py`; `register`/`get_flow` round-trip. Tests:
`tests/engine/test_registry.py`.

## T10 — Executor (advance) + public API
`app/engine/executor.py`: `advance(state, event, flow, *, ctx) -> FlowStepResult`
dispatching every `FlowEvent`, integrating steps/calendar/fy/followups/cache/
delivery/errors, driving a flow first-step → generate → deliver. Re-export the
public surface from `app/engine/__init__.py`.
**Done:** `advance` drives a full flow deterministically to delivery; a
stepper-edit clears downstream and refetches NOTHING until the generate step;
`resend` re-delivers bypassing the cache; the follow-up cap escalates on the 3rd.
Tests: `tests/engine/test_executor.py`.

## T11 — Suite green + doneCondition
`uv run pytest tests/engine/` green; every doneCondition clause has a covering
test. Reconcile any cross-cutting gaps, then request the fresh verifier panel.
**Done:** `pytest tests/engine/` exits 0; `uv run pytest` (full suite) still green.
