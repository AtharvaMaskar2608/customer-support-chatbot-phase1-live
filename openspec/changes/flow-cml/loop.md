# loop.md — flow-cml

Resume-from-this-file log for the flow-cml worktree lead. If it isn't here, it
didn't happen.

## Status: CORRECTIVE PR open — render-#4 chips (PR #16 merged the wrong version)
- **What happened**: PR #16 (branch `flow-cml`) was opened first with the frozen-
  taxonomy (T2) recovery chips. The operator then decided render-seq #4 (flow-
  specific 2-chip set). I implemented render-#4 and force-pushed it to `flow-cml`,
  BUT Gate 2 had already merged PR #16 at the earlier frozen commit (main merge
  `66563a3`) before that force-push could be part of the merge. Net: **main shipped
  the frozen chips, not render-#4**; PR #17 then merged on top (main @ `541e641`).
- **Fix**: a merged PR can't be reopened, so this ships render-#4 as a clean
  corrective PR — branch `flow-cml-render4-chips` off current main (`541e641`),
  cherry-picking only the render-#4 change (2 files). Gates: testCommand 16 passed;
  full `uv run pytest -q` = 591 passed, 1 skipped (live LLM).
- Escalated the mis-merge to the team lead.

## The decision being corrected (operator-approved, spec-authoritative)
- The approved proposal contradicted itself on CML failure recovery chips:
  render-seq #4 = [↺ Send it again · 🎫 Raise a ticket] (flow-specific, 2 chips);
  tasks.md T2 = render recovery chips verbatim from frozen `ERROR_COPY`.
- Frozen `errors.py` makes these incompatible (retry label "↺ Retry"/"↺ Try again";
  E-FETCH set carries "✉️ Email me both", a dead chip for a PDF-only/no-email flow).
- **Decision: render-#4 wins.** Implementation in this corrective PR:
  - `_error_block` renders the flow-specific `recovery_chips()` for every code; error
    TEXT stays frozen verbatim.
  - `CmlFlow.recovery_chips` returns the same set (dangling `_chips_from_labels`
    NameError removed).
  - Recovery-chip test asserts render-#4's set per the proposal, renamed
    `test_recovery_chips_are_flow_specific_per_render4`, with an inline note that this
    is a deliberate operator-approved spec-authoritative resolution (not silent T2
    deviation).

## Change
- Change ID / branch: `flow-cml` (original, MERGED frozen via PR #16) →
  corrective branch `flow-cml-render4-chips` (render-#4).
- Owner files (manifest): `app/flows/cml.py`, `tests/flows/test_cml.py`.

## Key design decisions (unchanged from the original flow)
- Registration via module-level `FLOW` (frozen `FlowSpec`), engine importlib
  discovery; NO edit to `app/flows/__init__.py`; PEP 420 namespace.
- Intent `Intent.report_cml`. JWT/MIS adapter; SessionId never used.
- FLAG B: signed `cmlLink` fetched server-side and discarded; never
  cached/logged/surfaced (tested).
- Filename carve-out `Client_Master_List.pdf` (§2.6); `password_hint=None`
  ([ASSUMPTION] unprotected, §9 item 12).

## Progress
- [x] T1–T3 — scaffold, `app/flows/cml.py`, `tests/flows/test_cml.py` (16 tests).
- [x] T4 (original) — shipped PR #16; MERGED at Gate 2 but with the FROZEN chips.
- [x] T5 (corrective) — render-#4 applied on branch `flow-cml-render4-chips` off
  main `541e641`; testCommand 16 passed; full suite 591 passed / 1 skipped;
  corrective PR opened (link below).

## Current task
DONE — corrective PR open for render-#4. Awaiting Gate 2 merge; the mis-merge was
reported to the team lead.

## Verifier rounds
- No verifier panel / self-check (owner tests-green directive).
- Gate: `pytest tests/flows/test_cml.py` = 16 passed; full `uv run pytest -q` on the
  corrective branch = 591 passed, 1 skipped.

## Metrics
- Verifier rounds used: 0 (tests-green directive).
- testCommand: 16 passed. Full harness (on 541e641 + render-#4): 591 passed, 1 skipped.
- Rebases/cherry-pick: original branch rebased twice cleanly; corrective branch is a
  clean cherry-pick of the render-#4 commit onto current main (0 conflicts).
- Escalations: 2 — (1) error-chip contradiction → resolved render-#4; (2) PR #16
  merged the frozen version instead of render-#4 → corrective PR (this).
- PRs: #16 (MERGED, frozen — superseded) + corrective PR __CORRECTIVE_PR__.
