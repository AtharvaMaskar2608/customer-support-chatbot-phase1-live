# Tasks: flow-brokerage

Single-shot Brokerage data-card flow. Two owned files only:
`app/flows/brokerage.py` + `tests/flows/test_brokerage.py` (empty
`tests/flows/__init__.py` created only if pytest needs the package).

- [ ] T1 — Scaffolding: `tasks.md` + `loop.md` (this commit).
- [ ] T2 — `app/flows/brokerage.py`: `FLOW` object satisfying the frozen
      `FlowSpec` (intent=`report_brokerage`, no-step `steps()`), the single-shot
      async handler (`get_brokerage_slab` on the JWT/go adapter with
      `{ClientID}`, one silent retry, dynamic `DataCard` with `desc` verbatim,
      conversational `E-TIMEOUT` error bubble), and the card-only edge-case
      builders (EC-4 off-plan, EC-5/6 calculation pointer, EC-7 no-document).
      No PDF/email path, no computed rupee figure, no URL/email on the card.
- [ ] T3 — `tests/flows/test_brokerage.py`: fixture-based tests written FROM
      the proposal — multi-segment success (frozen fixture), a variant fixture
      with a different segment set / row count (proves no hardcoding), a failure
      fixture (proves one silent retry then the error bubble), verbatim `desc`,
      no computed figure, no PDF/email/URL, `FLOW` discovery + `FlowSpec`
      conformance.
- [ ] T4 — Green: `pytest tests/flows/test_brokerage.py` + full `uv run pytest`.
- [ ] T5 — Fresh spec-verifier (single combined-lens per owner FAST VERIFY),
      fix blocking findings, second verifier if needed (bound 2).
- [ ] T6 — Rebase onto latest origin/main, full `uv run pytest` green, push, PR.
