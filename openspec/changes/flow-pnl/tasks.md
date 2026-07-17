# Tasks: flow-pnl

The P&L flow is a self-contained `FlowDefinition` built against the frozen
contracts (`app/contracts/**`, `app/finx/**`) and exercised with a minimal fake
engine driver in tests. The generic engine mechanics (step executor, byte-fetch
+ silent retry, 15-min cache, calendar rendering, authoritative delivery/error
assembly) are owned by `flow-engine-runtime` and integrated in Wave 2 — this
module provides only P&L-specific declarations and render/request builders.

- [ ] **T1 — Scaffold + registration.** `app/flows/pnl.py` exposing a
  module-level `FLOW: FlowSpec` (intent `report_pnl`, `config` with the frozen
  `DateWindow` floor `2018-01-01` / cap `today+7` / `max_range_years=2`,
  ordered `steps()` = segment → date_range → delivery). No edit to
  `app/flows/__init__.py`. Create empty `tests/flows/__init__.py`.
- [ ] **T2 — FinX request building.** Segment → `Group` (`Cash`/`Derv`/`Comm`,
  never surfaced), `Delivery` → `RequestFor` (0 download / 1 email), identity
  trap (`UserId == ClientId == client_id`, session-gated), `With_Exp=True`
  (boolean), no `FileFormat` (PDF only). Date-preset resolution (This FY / This
  Month / Last 3 months) via the frozen FY helpers + custom range → typed
  `PnlPdfRequest`.
- [ ] **T3 — Date-window guardrail.** Calendar bounds from config (floor
  `2018-01-01`, cap `today+7`), dynamic 2-year clamp (`clamp_end(start)` =
  start+2y exact), defensive `validate_range` with the flow's nudge copy
  ("I can fetch from Jan 2018 onwards…").
- [ ] **T4 — Render blocks + copy + masking.** Customer-facing chip rows
  (Equity/F&O/Commodity; This FY/This Month/Last 3 months/Custom range; PDF
  here/Email me), ack + generating copy, file card (renamed `PnL_<Segment>_<range>.pdf`,
  `password: PAN`, helper), email confirmation with masked registered email
  (`san***.harsha@gmail.com`), free-text pre-fill confirm, post-delivery chips.
- [ ] **T5 — Response + error handling.** Polymorphic `Response` (download URL
  vs email confirmation) via the frozen parser; outcome/exception → `E-*` code;
  render the bubble from the frozen `error-taxonomy` copy (emit codes, never
  redefine copy). Security: URL / `file_id` / server filename never reach the
  client or logs.
- [ ] **T6 — Tests from the proposal.** `tests/flows/test_pnl.py` — fixture
  fake-driver full walk (PDF + email), request-contract assertions, E-* mapping,
  calendar bounds/clamp, masking, security, discovery/`FlowSpec`.

doneCondition / testCommand: per `manifest.yaml`.
