# loop.md — flow-pnl

Worktree lead loop state. If it isn't here, it didn't happen.

## Assignment
- Change: `flow-pnl` (Wave 1). Branch/worktree `/home/choice/projects/customer-support/flow-pnl`, forked from main @ `cfb22a1` (contracts-foundation merged).
- Files owned (only these): `app/flows/pnl.py`, `tests/flows/test_pnl.py` (+ empty `tests/flows/__init__.py` if absent — identical adds merge cleanly).
- Frozen (never edit): `app/contracts/**`, `app/finx/*.py`, `app/llm/client.py`, `app/config/**`, `app/main.py`, `app/store/migrations/**`, `pyproject.toml`, `uv.lock`, `app/flows/__init__.py`.
- testCommand: `pytest tests/flows/test_pnl.py`. Full harness: `uv run pytest`.

## Design decisions (from proposal + frozen contracts + engine proposal)
- The engine (`flow-engine-runtime`, parallel) owns generic mechanics: step executor, byte-fetch+silent-retry (`app/finx/adapters` + engine retry policy), 15-min cache, calendar render, authoritative delivery/error assembly. The P&L module is a **self-contained FlowDefinition** providing P&L-specific declarations + request/render builders, tested with a **minimal fake driver**. Wave 2 integrates against the real engine.
- `FlowSpec` (frozen) is minimal: `intent`, `config`, `steps()`. My `FLOW` satisfies it AND carries flow-specific builders the engine will call at integration. No frozen `FlowDefinition` type exists yet (engine defines it) — I build to the frozen contracts and flag the engine coupling as a Wave-2 integration item.
- Error copy: IMPORTED from frozen `app.contracts.errors.ERROR_COPY` and emitted verbatim — never redefined (engine proposal rule).
- Flow-owned copy (chip labels, ack/generating, file-card caption, email confirmation, out-of-range nudge) lives here (engine proposal: "the flow's nudge copy").
- Masking: `mask_registered_email` implemented here as flow display logic per this proposal's "Email branch masks the registered email". The engine proposal also lists masking under generic delivery assembly → **potential Wave-2 dedup** (no file collision; pure helper). Flagged.
- Scrip-wise detail ("Global Report") post-delivery hand-off: **DEFERRED** per proposal §Why (GetDetailedPNL has no captured file endpoint [GAP]). Post-delivery chips = Email it + Raise a ticket only.

## Tasks
- [x] T0 — Read proposal, manifest, frozen contracts, fixtures, spec §8, FinX §4.1, parallelization plan. Baseline `uv run pytest` = 82 passed.
- [x] T1 — scaffold + registration (module-level `FLOW: PnlFlow` satisfies FlowSpec; config floor 2018-01-01/cap+7/2yr; steps segment→date_range→delivery). Created `tests/flows/__init__.py` empty (dir didn't exist). `app/flows/__init__.py` NOT created (engine-owned; `app.flows` imports as a namespace package until the engine lands it).
- [x] T2 — FinX request building (`build_request`: Group Cash/Derv/Comm, `UserId==ClientId` session-gated, RequestFor 0/1 via `REQUEST_FOR`, `With_Exp=True`, no FileFormat; `resolve_preset` This FY via frozen `current_fy` / This Month / Last 3 months).
- [x] T3 — date-window guardrail (`build_calendar` floor/cap; `clamp_end` = start+2y exact incl. leap; `validate_range` → flow nudge copy for the free-text path).
- [x] T4 — render blocks + copy + masking (segment/date/delivery chip rows w/ customer labels; ack/generating; file card renamed `PnL_<Seg>_<range>.pdf` password PAN; `email_confirmation` masked; `mask_registered_email` → `san***.harsha@gmail.com`; post-delivery chips; scrip-wise DEFERRED).
- [x] T5 — response + error handling (`delivery_kind` via frozen FileDeliveryResponse; `is_session_expiry` for 401; `error_code_for_envelope` no_data→E-NODATA / error→E-UNKNOWN; `render_error` emits frozen ERROR_COPY incl. E-FETCH second line; `fetch_retry_notice`).
- [x] T6 — `tests/flows/test_pnl.py` (22 tests, fake-driver). Fixed one test-only false positive ("Comm" is a substring of the label "Commodity"; assert the real leak tokens "Derv"/"Cash" + payload segment values instead). testCommand `pytest tests/flows/test_pnl.py` = 22 passed. Full `uv run pytest` = 104 passed (82 baseline + 22).
- [~] Verify: fresh spec-verifier panel — SKIPPED per human-operator lean directive (cut agent/token overhead; trust implementation, no self-check read-through). Not a convergence claim; 0 verifier rounds run.
- [x] Ship: rebased onto latest origin/main (b727d53, incl. PR #2/#3/#4/#5), full harness green, PR #12 opened.

## Current task
SHIPPED — see Ship section below.

## Verifier rounds
None. Lean no-panel directive from human operator: skip fresh-verifier panel AND self-check spec read-through, trust implementation. Only a real test failure is a blocker. No divergence hunting performed by this worktree lead.

## Open questions / integration notes
- [GAP] Scrip-wise detail post-delivery hand-off deferred (no GetDetailedPNL file endpoint).
- [INTEGRATION] Engine `FlowDefinition` interface not frozen — Wave 2 wires this flow's builders into the real engine; masking/error-render/calendar may dedup against engine's generic versions (no file collision).

## Ship
- Status: **SHIPPED** — PR #12 (https://github.com/AtharvaMaskar2608/customer-support-chatbot-phase1-live/pull/12)
- Rebased flow-pnl (fork @ cfb22a1) onto latest origin/main @ b727d53 (contains PR #2 finx-http-adapters, PR #3 flow-brokerage, PR #4 conversation-orchestrator, PR #5 flow-contract-notes). Clean rebase — only shared file `tests/flows/__init__.py` (identical empty add); `app/flows/pnl.py` / `tests/flows/test_pnl.py` disjoint from sibling flow files.
- testCommand `uv run pytest tests/flows/test_pnl.py` = 22 passed on rebased head.
- Full behavior harness `uv run pytest` = **252 passed** on the b727d53-rebased head (230 integrated baseline from PR #2/#3/#4/#5 + 22 from this change).
- doneCondition: fixture-based full step walk (PDF + email), Group Cash/Derv/Comm mapping, RequestFor per branch, With_Exp, E-* mapping, 2018 floor / today+7 cap / 2yr clamp, masked email — all exercised by the 22 fake-driver tests. Real-engine discovery/registration is the Wave-2 integration item (engine `FlowDefinition` not yet frozen).

## Metrics
- Verifier rounds used: 0 (skipped per lean no-panel directive).
- Findings per round: n/a.
- Escalations: 0.
- Implementation rounds: 1 (T1–T6, no rework beyond one test-only false-positive fix in T6).
- Rebases: 2 (first onto 9b6d31e = PR #2/#3; main advanced mid-ship, re-rebased onto b727d53 = +PR #4/#5), 0 conflicts either time.
- Harness runs: testCommand ×3, full suite ×2 (197 on 9b6d31e head, 252 on final b727d53 head — both green).
