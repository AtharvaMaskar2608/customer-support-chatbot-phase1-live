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
- [ ] T1 — scaffold + registration (FLOW/FlowSpec, config, steps)
- [ ] T2 — FinX request building (Group/identity/RequestFor/With_Exp/date presets)
- [ ] T3 — date-window guardrail (calendar bounds + 2yr clamp + nudge)
- [ ] T4 — render blocks + copy + masking
- [ ] T5 — response + error handling (polymorphic Response, E-* mapping, security)
- [ ] T6 — tests from proposal
- [ ] Verify: fresh spec-verifier panel
- [ ] Ship: rebase, full harness, PR

## Current task
T1 — scaffold (writing tasks.md + loop.md first commit).

## Verifier rounds
(none yet)

## Open questions / integration notes
- [GAP] Scrip-wise detail post-delivery hand-off deferred (no GetDetailedPNL file endpoint).
- [INTEGRATION] Engine `FlowDefinition` interface not frozen — Wave 2 wires this flow's builders into the real engine; masking/error-render/calendar may dedup against engine's generic versions (no file collision).
