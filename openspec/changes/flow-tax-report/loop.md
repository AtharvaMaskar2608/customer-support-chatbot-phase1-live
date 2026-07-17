# loop.md — flow-tax-report

Worktree lead loop state. If it isn't here, it didn't happen.

- Branch/worktree: `flow-tax-report` @ `/home/choice/projects/customer-support/flow-tax-report`
- Base: main @ `cfb22a1` (contracts-foundation merged; all consumed contracts frozen and present).
- testCommand: `pytest tests/flows/test_tax.py`
- doneCondition: full walk drives GetTaxReportPDF (dynamic FinYear, RequestFor
  2/1, FileFormat 1/2, two calls on email); CG/Tax-P&L prepend education + route
  here; AY→FY confirm; out-of-window FY → E-YEAR, no API call; string URL fetched
  server-side + byte-validated per format; "Data not available." → E-NODATA.
  Fixture-based mocks, no live API.

## Frozen surface used (read-only)
- `app/contracts/flow.py`: FY helpers (`current_fy`/`supported_fys`/`default_fy`/
  `fy_long_to_short`/`fy_short_to_long`), `FlowSpec`/`FlowConfig`/`DateWindow`/
  `Step`/`StepKind`, `ByteValidation`/`CacheConfig`, `MAGIC_BYTES`.
- `app/contracts/router.py`: `Intent`, `TAX_FLOW_INTENTS`, `EDUCATION_LINE_INTENTS`,
  `ReportFormat`, `Delivery`, `ExtractedParams`.
- `app/contracts/errors.py`: `ERROR_COPY`, `EC12`, `ErrorCode`.
- `app/contracts/wire.py`: `Bubble`/`ChipRow`/`Chip`/`ChipAction`/`ChipActionKind`/
  `ErrorBubble`/`FileCard`/`StepperCard`/`StepperStep`.
- `app/finx/models.py`: `TaxReportRequest`, `ENDPOINTS["GetTaxReportPDF"]`.
- `app/finx/interfaces.py`: `FinXClient`/`DotNetMiddlewareAdapter`.
- `app/finx/envelopes.py`: `ParsedEnvelope`, `Outcome`.

## Design decisions (against unfrozen engine executor — self-contained driver)
- Engine executor/cache/discovery is a parallel change (flow-engine-runtime); its
  runtime interface is NOT in contracts-foundation. So `tax.py` is a self-contained
  driver: `FLOW` satisfies the frozen `FlowSpec` for discovery, and the flow logic
  is driven directly by the test via explicit methods, injecting a fake FinX client
  and a fake byte-fetcher. This is the team-lead-sanctioned "own minimal fake driver".
- `app/flows/__init__.py` intentionally NOT created (frozen, engine-owned). Verified
  `import app.flows.tax` works as a PEP-420 namespace module without it.
- Three intents (report_tax / report_capital_gain / report_tax_pnl) all map to this
  one flow. `FLOW.intent = report_tax` (discovery key); `FLOW.handles()` +
  `TAX_FLOW_INTENTS` express the 3-intent claim; the original intent rides in
  `FlowState.intent`/driver args to pick the S0 education line.
- Fixtures: only `tests/fixtures/finx/tax_failure.json` pre-exists and success
  (PDF/Excel URL) fixtures do not; fixture files are NOT in my manifest filesTouched.
  Decision: keep everything in my 2 owned files — inline the fake FinX ParsedEnvelope
  responses in `test_tax.py`. No new shared fixture files created (boundary-safe).
- auth_error (401) is not flow-owned (session/EC-7 is engine/orchestrator-level; the
  frozen 5-code taxonomy has no session code) → defensively mapped to E-UNKNOWN per
  the proposal's "other → E-UNKNOWN".

## Tasks
- [x] T1 — tasks.md + loop.md.
- [x] T2 — implement app/flows/tax.py (FLOW discovery, dynamic FY, S0 education,
  FY resolution incl. AY→FY + E-YEAR, format/delivery, GetTaxReportPDF calls,
  server-side byte-validated fetch + 1 silent retry, file/email cards, EC-12,
  error taxonomy). Smoke-checked: FLOW isinstance FlowSpec True.
- [x] T3 — tests/flows/test_tax.py (22 tests, all from the doneCondition) + empty
  tests/flows/__init__.py. testCommand green (22 passed); full suite green
  (104 passed, 1 pre-existing unrelated warning).
- [ ] T4 — fresh verifier + rebase + full harness + PR (in progress)

## Verifier rounds
- Round 1: pending (one fresh spec-verifier, all 3 lenses, proposal dir + branch diff).

## Open questions
- EC-9 (no registered email): flow supports `hide_email` in S2 and the refusal copy
  path; whether it can actually occur is [OPEN] in the spec — implemented defensively.

## Metrics
- Verifier rounds used: 0
- Escalations: 0
