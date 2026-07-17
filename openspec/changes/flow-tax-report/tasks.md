# Tasks: flow-tax-report

Implementation of the deterministic Tax / Capital-Gain report flow. Two owned
files only: `app/flows/tax.py` and `tests/flows/test_tax.py` (plus an empty
`tests/flows/__init__.py` if the test package needs it). `app/flows/__init__.py`
is NOT created here — the engine (flow-engine-runtime) owns the discovery
registry; `app/flows.tax` imports as a PEP-420 namespace module without it.

- [ ] T1 — Author `tasks.md` + `loop.md` (this commit).
- [ ] T2 — Implement `app/flows/tax.py`:
  - `FLOW` discovery object satisfying the frozen `FlowSpec` (intent =
    `report_tax`, `config` fy-based, `steps()` = FY + format/delivery); claims all
    three `TAX_FLOW_INTENTS`.
  - Dynamic FY model via the frozen FY helpers (never hardcode years).
  - S0 education line (CG / Tax-P&L only), verbatim per flow-spec §4.1.
  - S1 FY resolution: chip select, free-text pre-filled confirm, AY→FY explicit
    confirm (EC-2), out-of-window → E-YEAR with the 3 FY chips and NO API call
    (EC-1).
  - S2 format & delivery (PDF here / Excel here / Email both), EC-9 hide-email.
  - Generate: `GetTaxReportPDF` with dynamic `FinYear`, `RequestFor` (2 download /
    1 email), `FileFormat` (1 PDF / 2 Excel; two calls on email). Server-side URL
    fetch + magic-byte/size validation, one silent auto-retry, then E-FETCH. File
    card (renamed, no password) or masked email-sent card. EC-12 partial email.
  - Error mapping: no_data → E-NODATA, out-of-window → E-YEAR, timeout →
    E-TIMEOUT, bad bytes → E-FETCH, other → E-UNKNOWN. URLs/Reasons never surfaced.
- [ ] T3 — Write `tests/flows/test_tax.py` from the proposal doneCondition
  (fixture/fake FinX driver; offline). Assert every doneCondition clause.
- [ ] T4 — Run `pytest tests/flows/test_tax.py` + full suite; fresh verifier
  panel; fix; rebase onto origin/main; full pytest green; PR.
