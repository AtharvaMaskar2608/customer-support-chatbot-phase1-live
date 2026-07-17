# loop.md — flow-brokerage

Worktree: `/home/choice/projects/customer-support/flow-brokerage`
Branch: `flow-brokerage` (from main @ cfb22a1, contracts-foundation merged)
Owned files (manifest): `app/flows/brokerage.py`, `tests/flows/test_brokerage.py`
(+ empty `tests/flows/__init__.py` only if pytest requires the package —
authorized by the team-lead task message).

## Contract anchors (frozen, read-only — verified in source)

- Intent: `Intent.report_brokerage` (app/contracts/router.py). The proposal's
  shorthand "Intent.BROKERAGE" == this frozen value; no new intent is added.
- FLOW registration: module-level `FLOW` satisfying `FlowSpec` Protocol
  (`intent`, `config: FlowConfig`, `steps() -> Sequence[Step]`) —
  app/contracts/flow.py. Discovery is importlib by module presence;
  `app/flows/__init__.py` is engine-owned and NOT created here (namespace-package
  import of `app.flows.brokerage` verified working without it).
- Adapter call: `finx.go.get_brokerage_slab(BrokerageSlabRequest(ClientID=...))`
  → `ParsedEnvelope` (app/finx/interfaces.py, models.py, envelopes.py). Request
  key is PascalCase one-word `ClientID`. Hybrid envelope parsed via the dotnet
  parser keyed on `Status`; adapter returns a `ParsedEnvelope` with
  `outcome`/`payload`/`reason`.
- Response: `payload` = array of `{title, list:[{title, desc}]}`
  (`BrokerageGroup`/`BrokerageRow`). `desc` is pre-formatted rate text.
- Render: `DataCard(groups=[DataGroup(title, list=[DataRow(label, value)])])`
  from app/contracts/wire.py — `value` VERBATIM (frozen wire test
  tests/contracts/test_wire.py asserts value == raw desc). Card carries no
  URL/email (frozen FORBIDDEN_KEYS test).
- Error: conversational `ErrorBubble(code, text, chips)`; recovery chips live on
  the bubble. Brokerage uses flow-spec copy (not the report E-* file taxonomy);
  code = `E_TIMEOUT` (best-fit: API/fetch failure; chips match).

## Design decisions

- Single-shot: `steps()` returns `()`; no stepper/calendar/file-card/email.
- Failure detection (per proposal): transport exception OR non-success outcome
  OR missing/empty `Response` array → one silent retry → error bubble.
- Edge-case builders (proposal "What Changes" + render sequence), card-only:
  EC-7 no-document (email/PDF ask), EC-4 off-plan (re-show plan + ticket),
  EC-5/6 calculation pointer (rates not amounts → contract note; never compute).
- Fixtures: multi-segment = frozen tests/fixtures/finx/brokerage_hybrid_success.json;
  variant (different segment set/row count) + failure defined INLINE in the test
  file (stays within the two-file manifest boundary).

## Progress log

### Round 0 — scaffolding
- T1 DONE: tasks.md + loop.md authored. Contracts read end-to-end; namespace
  import of `app.flows.brokerage` verified without `app/flows/__init__.py`.

### Round 1 — implementation + tests
- T2 DONE: `app/flows/brokerage.py` — `FLOW`/`BrokerageFlow` (FlowSpec-conformant,
  no-step), single-shot `handle()` (one `get_brokerage_slab` call keyed by
  `ClientID`, one silent retry, dynamic verbatim `DataCard`, `E_TIMEOUT` error
  bubble), and the card-only edge builders (EC-4/EC-5-6/EC-7). No file/email path.
- T3 DONE: `tests/flows/test_brokerage.py` (+ empty `tests/flows/__init__.py` to
  match the sibling test-dir package convention). 15 tests written from the
  proposal: FlowSpec conformance, single call + `ClientID` key trap, frozen
  multi-segment fixture verbatim, inline variant (2 segments / 1+3 rows) proving
  no hardcoding, no URL/email on card, one-silent-retry-then-error, transient
  recovery, empty-`Response` failure, transport-exception failure, no
  file/email block on any path + static FileCard guard, EC-4/5-6/7 builders.
- T4 DONE: `pytest tests/flows/test_brokerage.py` = 15 passed; full
  `uv run pytest` = 97 passed.
- Current task: T5 (fresh spec-verifier).

## Verifier rounds
- (none yet — Round 1 verifier pending)

## Open questions / escalations
- (none)
