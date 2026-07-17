# loop.md — flow-cml

Resume-from-this-file log for the flow-cml worktree lead. If it isn't here, it
didn't happen.

## Status: BLOCKED — escalated to team lead (spec ambiguity on error-recovery chips)
Committed HEAD (`d8878fe`) is GREEN (`pytest tests/flows/test_cml.py` → 16 passed).
NOT rebased, NOT shipped. Waiting on a team-lead decision (see Escalation below).

## Change
- Change ID / branch / worktree: `flow-cml`
- Base: main @ cfb22a1 (contracts-foundation merged, PR #1). NOTE: origin/main has
  since advanced (finx-http-adapters PR #2, flow-brokerage PR #3). Rebase deferred
  until unblocked.
- Owner files (manifest): `app/flows/cml.py`, `tests/flows/test_cml.py`
  (+ authorized empty `tests/flows/__init__.py`)
- Mode: LEAN verify (owner directive 2026-07-17) — one fresh self-check by the
  worktree lead (all three lenses), NO 3-agent verifier panel this pass.

## Key design decisions (from frozen contracts + all-six-flows reconcile read)
- **Registration**: module-level `FLOW` satisfying the frozen minimal `FlowSpec`
  (`app/contracts/flow.py`: intent, config, `steps()`); engine auto-discovers via
  importlib. NO edit to `app/flows/__init__.py` (engine-owned/frozen). `app/flows`
  is a PEP 420 namespace package — import verified working without an `__init__`.
- **Intent name**: frozen enum is `Intent.report_cml` (the proposal's shorthand
  "Intent.CML"). Frozen surface wins.
- **Division of labor**: the engine (change 2) owns the *generic* runtime
  (byte-validation/retry/delivery/error-mapping) for all six flows; my proposal's
  doneCondition is standalone-testable, so `cml.py` implements its own cohesive
  generation path **reusing frozen shared semantics** — `ByteValidation`,
  `PDF_MAGIC`, `ERROR_COPY`, `ErrorCode`, and the `chat-wire-api` render types —
  and never redefines error copy (emits codes; renders bubble text from frozen
  `ERROR_COPY`).
- **Byte-fetch**: no `fetch_report_bytes` helper is frozen/present (it lands with
  change 1). To stay parallel-safe + offline the flow takes an **injected async
  fetcher** `Callable[[str], Awaitable[bytes]]`; tests inject a fake. FLAG B: the
  signed URL is fetched server-side and discarded — never cached/logged/surfaced.
- **FLAG B (security-critical)**: `cmlLink` never enters a render block (frozen
  `FileCard` has no url field and forbids extra), never logged. Enforced + tested
  (`test_link_never_surfaced_in_any_block` — green).
- **Filename carve-out**: keep server filename `Client_Master_List.pdf` (§2.6).
- **Password**: `password_hint=None` — [ASSUMPTION] CML PDF unprotected (spec §9
  item 12) encoded verbatim as a [CONFIRM].

## Open questions / [CONFIRM] / [GAP] / Escalations
- **[BLOCKER — ESCALATED 2026-07-17] Error-recovery-chip spec contradiction.**
  The approved proposal is internally inconsistent about CML failure recovery chips:
  - `proposal.md` render-sequence **#4** says: failures → error-bubble + recovery
    chip-row **[↺ Send it again · 🎫 Raise a ticket]** (flow-specific, 2 chips).
  - `tasks.md` **T2** says: "Render ErrorBubble text + recovery chips **from frozen
    `ERROR_COPY`** (do NOT redefine copy)."
  These cannot both hold, because frozen `app/contracts/errors.py` (Wave-0) defines:
    - `E_UNKNOWN.chips = ("↺ Retry", "🎫 Raise a ticket")`
    - `E_TIMEOUT.chips = ("↺ Retry", "🎫 Raise a ticket")`
    - `E_FETCH.chips  = ("↺ Try again", "✉️ Email me both", "🎫 Raise a ticket")`
  i.e. the frozen retry label is "↺ Retry"/"↺ Try again" (not "↺ Send it again"),
  and frozen **E-FETCH carries "✉️ Email me both"** — nonsensical for CML, which is
  PDF-only with no email/dual-format path.
  - **Committed HEAD follows T2/frozen** (`_error_block` → `_chips_from_labels`
    renders frozen chips verbatim). The from-proposal test
    `test_recovery_chips_come_from_frozen_taxonomy` asserts this (E_UNKNOWN) and is
    GREEN. doneCondition (correct E-* codes) is satisfied.
  - **Consequence of the frozen reading**: a CML E-FETCH error surfaces an
    "✉️ Email me both" chip that does nothing sensible — the exact defect render-#4
    was written to avoid.
  - **Stray in-progress work found**: an UNCOMMITTED, unrecorded working-tree edit
    was pursuing the render-#4 reading (replace `_chips_from_labels` with a
    flow-specific `recovery_chips()`), but was HALF-FINISHED and BROKEN — it deleted
    `_chips_from_labels` while `CmlFlow.recovery_chips` (cml.py:238) still calls it
    (NameError), and it did not update the test (→ 1 failing test). I safely
    **stashed** it (`git stash`, message references this loop.md); working tree is
    now clean at green HEAD. Recover with `git stash list` / `git stash show -p`.
  - **Recommendation to team lead**: render-#4 is likely the intended product
    behavior (avoids the "Email me both" chip on CML). Adopting it cleanly means
    (a) finishing the stashed change + fixing/removing `CmlFlow.recovery_chips`, and
    (b) reconciling `test_recovery_chips_come_from_frozen_taxonomy` to assert
    render-#4's chips FROM the proposal — a spec-authoritative test change I will not
    make unilaterally. Alternatively, if the frozen taxonomy is authoritative, ship
    HEAD as-is (green) and accept/track the E-FETCH "Email me both" chip.
    Awaiting the team lead's call on which interpretation ships.
- [CONFIRM] CML PDF password status (assumed unprotected) — carried from proposal.
- [CONFIRM] `source: FINX_ANDROID` gating + generic report-generator shape — owned
  by the MIS/JWT adapter (change 1), not this flow.
- [GAP/NOTE] The engine↔flow execution binding (`FlowDefinition`, adapter-binding
  signature, delivery assembly) is NOT frozen in contracts-foundation; only minimal
  `FlowSpec` is. cml.py exposes both the frozen `FlowSpec` surface AND
  clearly-named declarations (`DISPLAY_FILENAME`, `PASSWORD_HINT`, `FILE_FORMAT`,
  chip builders, `run()`) so the engine can drive it once its binding lands. If the
  engine's final binding differs, integration wiring is the engine/orchestrator's
  concern (later wave). Flagged for the team lead.

## Progress
- [x] T1 — scaffold: tasks.md + loop.md (commit fd39e6f); empty
  `tests/flows/__init__.py` (commit 34c6d9a).
- [x] T2 — implement `app/flows/cml.py` (commit 6763950). Imports clean;
  `isinstance(FLOW, FlowSpec)` True; `FLOW.intent == Intent.report_cml`.
- [x] T3 — `tests/flows/test_cml.py` (commit 34c6d9a): 16 tests.
- [~] T4 — LEAN self-check DONE (round 1 below). testCommand GREEN on committed
  HEAD. BLOCKED before rebase/ship on the error-chip spec contradiction above.

## Current task
T4 — BLOCKED. Escalated the error-chip spec contradiction to the team lead. Do NOT
rebase, run full suite, or open the PR until the interpretation is decided. When
unblocked: implement the chosen reading (if render-#4: unstash + finish + reconcile
the one test), re-run testCommand, rebase onto origin/main, run full `uv run
pytest`, push, open PR.

## Verifier rounds
- **Round 1 — LEAN self-check (worktree lead, all three lenses; per owner
  directive, no 3-agent panel).** Scope: proposal.md/design(n/a)/tasks.md +
  `git diff main...HEAD` + testCommand.
  Findings:
  1. (BLOCKING) Error-recovery-chip spec contradiction — render-#4 vs T2/frozen
     `ERROR_COPY`; E-FETCH frozen chips include an inapplicable "✉️ Email me both"
     for CML. → ESCALATED (see Open questions). Not fixed by me (spec-authoritative).
  2. (BLOCKING, secondary — a symptom of #1) Stray uncommitted, unrecorded,
     half-finished working-tree edit broke `CmlFlow.recovery_chips` (undefined
     `_chips_from_labels` → NameError) and the test suite (1 failing). → SAFELY
     STASHED; working tree restored to clean green HEAD.
  3. (OK) Frozen-file / manifest boundary: `git diff --name-only main...HEAD` touches
     only owned files (`app/flows/cml.py`, `tests/flows/*`) + openspec/. No frozen
     contract, `app/flows/__init__.py`, adapter, lockfile, or root-config edits.
  4. (OK) doneCondition items present on HEAD: discovery/registration; JWT request
     shape (`reportType:cml`/`searchBy:client-id`/`searchValue=ctx.user_id`, no
     SessionId); server-side fetch + `%PDF` byte-validate; `Client_Master_List.pdf`
     no-password delivery; link never surfaced/logged; resend re-calls API; correct
     E-* codes for auth/fetch/timeout/unknown. All covered by green tests.

## Metrics
- Verifier rounds used: 1 (lean self-check; no panel per owner directive)
- Findings this round: 2 blocking (1 spec contradiction → escalated; 1 stray broken
  edit → stashed), plus boundary/doneCondition confirmed OK.
- Escalations: 1 (spec contradiction on error-recovery chips) + the pre-existing
  engine↔flow binding GAP note (non-blocking).
- testCommand on committed HEAD: 16 passed. Full behavior harness: NOT yet run
  (gated on rebase, which is gated on the escalation).
