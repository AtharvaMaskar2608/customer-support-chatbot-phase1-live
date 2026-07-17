# loop.md — flow-cml

Resume-from-this-file log for the flow-cml worktree lead. If it isn't here, it
didn't happen.

## Status: SHIPPED — PR #16 (lean tests-green path), Gate 2 pending
- Directive (2026-07-17, human operator via team lead), superseding earlier passes:
  skip the fresh self-check / spec-divergence review; the gate is tests-green. Run
  testCommand → rebase onto origin/main → full `uv run pytest -q` → if green, ship.
  Only BLOCK on actually-failing tests, real rebase conflicts, or a stale loop.md
  hiding unfinished implementation tasks.
- Result: testCommand GREEN (16 passed). Rebased onto origin/main `ecb6ac3` cleanly
  (no conflicts). Full repo suite GREEN (312 passed). No unfinished impl tasks. → SHIP.
- The earlier error-recovery-chip escalation is intentionally DEFERRED to Gate 2
  (human PR review) per this directive — carried forward in the PR body, NOT a
  blocker. Detail retained under "Open questions" below.

## Change
- Change ID / branch / worktree: `flow-cml`
- Base after rebase: origin/main @ `ecb6ac3` (through PR #7). Earlier base cfb22a1.
- Owner files (manifest): `app/flows/cml.py`, `tests/flows/test_cml.py`
  (+ authorized empty `tests/flows/__init__.py`)
- Ship mode: LEAN tests-green (owner directive) — no verifier panel, no self-check.

## Key design decisions (from frozen contracts + all-six-flows reconcile read)
- **Registration**: module-level `FLOW` satisfying the frozen minimal `FlowSpec`
  (`app/contracts/flow.py`); engine auto-discovers via importlib. NO edit to
  `app/flows/__init__.py`. `app/flows` is a PEP 420 namespace package.
- **Intent name**: frozen enum `Intent.report_cml`.
- **Division of labor**: `cml.py` implements its own cohesive generation path
  reusing frozen shared semantics (`ByteValidation`, `PDF_MAGIC`, `ERROR_COPY`,
  `ErrorCode`, `chat-wire-api` render types); never redefines error copy.
- **Byte-fetch**: injected async fetcher `Callable[[str], Awaitable[bytes]]`;
  tests inject a fake. FLAG B: signed URL fetched server-side and discarded.
- **FLAG B (security-critical)**: `cmlLink` never enters a render block, never
  logged. Enforced + tested (`test_link_never_surfaced_in_any_block` — green).
- **Filename carve-out**: keep server filename `Client_Master_List.pdf` (§2.6).
- **Password**: `password_hint=None` — [ASSUMPTION] CML PDF unprotected (§9 item 12).

## Open questions / [CONFIRM] / [GAP] — deferred to Gate 2 per directive
- **[DEFERRED to Gate 2] Error-recovery-chip proposal contradiction (non-blocking
  per 2026-07-17 tests-green directive).** proposal render-seq #4 lists CML recovery
  chips as [↺ Send it again · 🎫 Raise a ticket]; tasks.md T2 says render recovery
  chips verbatim from frozen `ERROR_COPY`. Frozen `errors.py` makes these
  incompatible: retry label is "↺ Retry"/"↺ Try again", and E-FETCH.chips include
  "✉️ Email me both" — nonsensical for PDF-only CML. **Shipped HEAD follows
  T2/frozen** (`_error_block`→`_chips_from_labels`, renders frozen chips verbatim;
  green test `test_recovery_chips_come_from_frozen_taxonomy`). Consequence: a CML
  E-FETCH error surfaces a dead "Email me both" chip. Flagged in the PR body for the
  human reviewer to rule on at Gate 2.
- **[STASH] Stray render-#4 attempt preserved in `git stash` (was `stash@{0}` pre-
  rebase; recover via `git stash list`).** A half-finished, unrecorded working-tree
  edit that switched to flow-specific recovery chips but broke `CmlFlow.recovery_chips`
  (deleted a helper it still calls) + 1 test. NOT applied; retained in case Gate 2
  chooses the render-#4 reading.
- [CONFIRM] CML PDF password status (assumed unprotected) — carried from proposal.
- [CONFIRM] `source: FINX_ANDROID` gating + generic report-generator shape — owned
  by the MIS/JWT adapter (change 1).
- [GAP/NOTE] engine↔flow execution binding not frozen in contracts-foundation; only
  minimal `FlowSpec` is. cml.py exposes both the frozen `FlowSpec` surface and
  clearly-named declarations so the engine can drive it once its binding lands.

## Progress
- [x] T1 — scaffold: tasks.md + loop.md; empty `tests/flows/__init__.py`.
- [x] T2 — implement `app/flows/cml.py` (zero-step CML flow).
- [x] T3 — `tests/flows/test_cml.py`: 16 tests.
- [x] T4 — SHIP (lean tests-green): testCommand 16 passed; rebased onto ecb6ac3
  clean; full suite 312 passed; pushed + PR opened (link below).

## Current task
DONE — shipped via the lean tests-green path. PR open for Gate 2.

## Verifier rounds
- No verifier panel and no self-check this ship (owner tests-green directive).
- Gate: `pytest tests/flows/test_cml.py` = 16 passed; full `uv run pytest -q` on the
  rebased head = 312 passed.

## Metrics
- Verifier rounds used: 0 (tests-green directive; the one earlier lean self-check was
  superseded — its finding deferred to Gate 2, not counted as a verify round).
- testCommand: 16 passed. Full behavior harness (rebased onto ecb6ac3): 312 passed.
- Rebase: clean, 0 conflicts. Escalations: 1 earlier (error-chip contradiction) —
  resolved by the operator's tests-green directive (deferred to Gate 2).
- PR: #16 — https://github.com/AtharvaMaskar2608/customer-support-chatbot-phase1-live/pull/16
