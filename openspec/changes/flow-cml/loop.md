# loop.md — flow-cml

Resume-from-this-file log for the flow-cml worktree lead. If it isn't here, it
didn't happen.

## Status: SHIPPED — PR #16 (render-#4 resolution applied), Gate 2 pending
- Lean tests-green ship path (owner directive 2026-07-17): no verifier panel.
- Gate-2 design decision RESOLVED by the operator (via team lead, 2026-07-17):
  ship render-seq #4's flow-specific recovery chips, NOT the frozen taxonomy's
  generic set. Applied in commit "adopt render-#4 flow-specific error-recovery
  chips (Gate-2 resolution)". Re-shipped on PR #16 after rebase.
- Latest gate results: testCommand 16 passed; rebased onto origin/main `2daa87b`
  (through PR #15) cleanly; full `uv run pytest -q` = 591 passed, 1 skipped
  (live LLM test, JINI_RUN_LIVE gate).

## Change
- Change ID / branch / worktree: `flow-cml`
- Base after latest rebase: origin/main @ `2daa87b`.
- Owner files (manifest): `app/flows/cml.py`, `tests/flows/test_cml.py`
  (+ authorized empty `tests/flows/__init__.py`)
- Ship mode: LEAN tests-green (owner directive) — no verifier panel, no self-check.

## Key design decisions (from frozen contracts + all-six-flows reconcile read)
- **Registration**: module-level `FLOW` satisfying frozen `FlowSpec`; engine
  discovers via importlib. NO edit to `app/flows/__init__.py`. `app/flows` is a
  PEP 420 namespace package.
- **Intent name**: frozen enum `Intent.report_cml`.
- **Error copy**: emits `ErrorCode`s; renders TEXT verbatim from frozen `ERROR_COPY`.
  Recovery-chip SET is flow-specific per render-#4 (see resolution below).
- **Byte-fetch**: injected async fetcher; FLAG B — signed URL fetched server-side
  and discarded, never cached/logged/surfaced (tested).
- **Filename carve-out**: keep server filename `Client_Master_List.pdf` (§2.6).
- **Password**: `password_hint=None` — [ASSUMPTION] CML PDF unprotected (§9 item 12).

## Open questions / resolutions
- **[RESOLVED 2026-07-17 — operator-approved, spec-authoritative] CML error-recovery
  chips.** The approved proposal contradicted itself: render-seq #4 lists recovery
  chips as [↺ Send it again · 🎫 Raise a ticket] (flow-specific, 2 chips), while
  tasks.md T2 said render recovery chips verbatim from frozen `ERROR_COPY`. Frozen
  `errors.py` made these incompatible (retry label "↺ Retry"/"↺ Try again"; E-FETCH
  set carries "✉️ Email me both"). **Decision: adopt render-#4** — the frozen
  taxonomy's "Email me both" chip is a dead/nonsensical action for a PDF-only flow
  with no email path (a real UX bug render-#4 was written to avoid). Implementation:
  `_error_block` renders the flow-specific `recovery_chips()` for every code (TEXT
  still frozen verbatim); `CmlFlow.recovery_chips` returns the same set (dangling
  `_chips_from_labels` / NameError removed); the recovery-chip test was updated to
  assert render-#4's set per the proposal and renamed
  `test_recovery_chips_are_flow_specific_per_render4`, with an inline note on why it
  diverges from T2's literal frozen-taxonomy instruction. Also flagged in the PR body.
- **[STASH — CONSUMED]** The earlier stray render-#4 attempt (`git stash`) was
  recovered (`git stash pop`) and finished as part of this resolution. Stash empty.
- [CONFIRM] CML PDF password status (assumed unprotected) — carried from proposal.
- [CONFIRM] `source: FINX_ANDROID` gating + generic report-generator shape — owned
  by the MIS/JWT adapter (finx-http-adapters).
- [GAP/NOTE] engine↔flow execution binding: minimal `FlowSpec` is frozen;
  flow-engine-runtime (PR #13) has since landed on main and the full suite is green
  on the rebased head, so discovery integrates cleanly. cml.py exposes both the
  frozen `FlowSpec` surface and clearly-named declarations for the engine to bind.

## Progress
- [x] T1 — scaffold: tasks.md + loop.md; empty `tests/flows/__init__.py`.
- [x] T2 — implement `app/flows/cml.py` (zero-step CML flow).
- [x] T3 — `tests/flows/test_cml.py`: 16 tests.
- [x] T4 — SHIP (lean tests-green): PR #16 opened; then applied the operator's
  render-#4 Gate-2 resolution; rebased onto `2daa87b`; full suite 591 passed;
  re-pushed (force-with-lease) to PR #16.

## Current task
DONE — shipped; PR #16 updated with the render-#4 resolution. Awaiting Gate 2 merge.

## Verifier rounds
- No verifier panel / self-check this ship (owner tests-green directive).
- Gate: `pytest tests/flows/test_cml.py` = 16 passed; full `uv run pytest -q` on the
  rebased head = 591 passed, 1 skipped (live LLM).

## Metrics
- Verifier rounds used: 0 (tests-green directive).
- testCommand: 16 passed. Full harness (rebased onto 2daa87b): 591 passed, 1 skipped.
- Rebases: 2, both clean (0 conflicts) — onto ecb6ac3, then 2daa87b.
- Escalations: 1 (error-chip contradiction) → RESOLVED by operator (render-#4).
- PR: #16 — https://github.com/AtharvaMaskar2608/customer-support-chatbot-phase1-live/pull/16
