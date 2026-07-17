# loop.md — flow-ledger-mtf

Status: **SHIPPED** — PR #6 (https://github.com/AtharvaMaskar2608/customer-support-chatbot-phase1-live/pull/6), Gate 2 pending.

Worktree: `/home/choice/projects/customer-support/flow-ledger-mtf`
Branch: `flow-ledger-mtf` (rebased onto origin/main @ 9b6d31e — PR #2 finx-http-adapters
and PR #3 flow-brokerage merged; base was cfb22a1 / PR #1 contracts-foundation).
Owner directive (superseded): Wave 1 full fan-out; target PR ~30 min.
**Final directive (human operator, token-overhead cut): LEAN NO-PANEL — skip the
fresh-verifier panel AND the self-check spec read-through entirely; trust the
implementation. Ship on green testCommand + green full suite on rebased head.**

## Contract summary (frozen, read-only — verified present on main)

- `app/contracts/flow.py`: `FlowSpec` protocol (`intent`, `config`, `steps()`),
  `FlowConfig`/`DateWindow` (floor/cap_relative_days/max_range_years), `Step`/
  `StepKind`/`StepState`, `ByteValidation` (min_bytes 1024, %PDF magic,
  silent_retries 1), `CacheConfig`, `selection_cache_key`, FY helpers, `FLOW_ATTR`.
- `app/contracts/router.py`: `Intent.report_ledger` / `Intent.report_mtf_ledger`,
  `ExtractedParams`, `DateRange`, `Delivery`.
- `app/finx/models.py`: `LedgerPdfRequest` (ClientId/LoginId/Group="GROUP1"/
  Margin/FromDate/ToDate/RequestFor/SessionId), `FileDeliveryResponse`
  (is_email_confirmation/is_download_url), `ENDPOINTS["GetLedgerDetailsPDF"]`.
- `app/finx/interfaces.py`: `FinXClient.dotnet.get_ledger_details_pdf(req)
  -> ParsedEnvelope`. `app/finx/envelopes.py`: `Outcome` {success,no_data,
  auth_error,error}, `ParsedEnvelope`.
- `app/contracts/errors.py`: `ErrorCode` {E_NODATA,E_YEAR,E_TIMEOUT,E_FETCH,
  E_UNKNOWN}, `ERROR_COPY`.
- `app/contracts/wire.py`: render blocks `Bubble`/`ChipRow`/`Chip`/`ChipAction`/
  `Calendar`/`FileCard`/`ErrorBubble`, `RenderBlock` union.

## Key decisions / interpretations

- `app/flows/` is a **namespace package** (no `__init__.py` — that file is frozen,
  engine-owned by flow-engine-runtime and not yet landed). Verified
  `import app.flows.<mod>` works without it. `tests/flows/__init__.py` created
  empty (pytest package-import parity with tests/finx, tests/contracts).
- Report-type step has no dedicated `StepKind`; the frozen enum's `segment`
  is the generic categorical chip-row kind (test_flow.py: segment → chip row).
  Used for the report-type step, documented in code.
- `FlowSpec.intent` is singular; flow registers under `report_ledger` (primary)
  and drives `Margin` from the report-type step. Additive `intents` tuple exposed
  so a multi-intent discovery can also key `report_mtf_ledger`. **Integration
  note flagged to team lead** — routing `report_mtf_ledger` → this flow depends
  on flow-engine-runtime's discovery honoring `intents`.
- E-NODATA and E-FETCH use LEDGER-specific copy (proposal + spec §8/EC-1/EC-5);
  E-TIMEOUT/E-UNKNOWN reuse frozen `ERROR_COPY` (generic). MTF no-data uses the
  plain no-education copy (EC-2). Session-expiry (auth_error) is a Bubble+ChipRow
  (no E-code exists for it).

## Tasks completed

- [x] 1. Scaffold (this file + tasks.md).
- [x] 2. Implemented `app/flows/ledger.py` — `LedgerFlow` (FlowSpec, module-level
      `FLOW`), window (floor 2019-01-01 / cap today+7 / no clamp), steps, request
      builder (LoginId=client code, Group GROUP1, Margin 0/1, RequestFor 0/1),
      date presets + out-of-window nudge + future clamp + calendar, download driver
      (server-side fetch + byte validation + one silent retry) and email driver
      (masked address), E-* mapping (ledger E-NODATA/E-FETCH copy, MTF plain
      no-data, session-expiry bubble, E-TIMEOUT/E-UNKNOWN), friendly filename,
      no password line.
- [x] 3. Wrote `tests/flows/test_ledger.py` (32 tests) from the proposal + flow
      spec; `tests/flows/__init__.py` empty. Fixture-based envelopes via the real
      `parse_dotnet_envelope`.
- [x] 4. `pytest tests/flows/test_ledger.py` → 32 passed. Full `uv run pytest` →
      114 passed (82 baseline + 32). doneCondition items each covered by a test.

- [x] 5. Ship. Per LEAN NO-PANEL directive: verifier panel SKIPPED, self-check
      read-through SKIPPED. Rebased onto origin/main (9b6d31e, clean, no conflicts);
      testCommand green (32 passed); full repo suite green (207 passed) on rebased
      head; branch pushed; PR #6 opened.

## Current task

- Done. Awaiting Gate 2 human review on PR #6.

## Verifier rounds

- none — SKIPPED by explicit human-operator directive (lean no-panel, token-overhead
  cut). Implementation trusted; correctness rests on the 32 from-proposal tests +
  full-suite green on the rebased head.

## Final metrics

- Tasks completed: 5/5 (task 5 = ship; verifier sub-step waived by directive).
- Verifier panels run: 0 (waived). Findings: n/a. Escalations: 0.
- testCommand: `pytest tests/flows/test_ledger.py` → 32 passed.
- Behavior harness (full `uv run pytest -q`) on rebased head: 207 passed, 1 warning.
- Rebase: onto origin/main @ 9b6d31e, clean (no conflicts).
- Files: `app/flows/ledger.py` (668 LOC), `tests/flows/test_ledger.py` (488 LOC,
  32 tests), `tests/flows/__init__.py` (empty).

## Open questions / [CONFIRM] / [GAP]

- [CONFIRM] `Margin:1` MTF fidelity (byte-identical on no-MTF account) — encoded, unverified.
- [CONFIRM] `RequestFor:1` email branch untested — encoded, unverified.
- [CONFIRM] `Group` "GROUP1" case-sensitivity.
- [CONFIRM] date-window cap today+7.
- [INTEGRATION] `report_mtf_ledger` → this flow relies on discovery honoring the
  additive `intents` hint (flow-engine-runtime, not yet landed).
