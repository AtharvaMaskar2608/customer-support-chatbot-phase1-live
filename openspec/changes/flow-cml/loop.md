# loop.md — flow-cml

Resume-from-this-file log for the flow-cml worktree lead. If it isn't here, it
didn't happen.

## Change
- Change ID / branch / worktree: `flow-cml`
- Base: main @ cfb22a1 (contracts-foundation merged, PR #1)
- Owner files (manifest): `app/flows/cml.py`, `tests/flows/test_cml.py`
  (+ authorized empty `tests/flows/__init__.py`)
- Mode: FAST verify (owner-approved) — one fresh spec-verifier covering all three
  lenses; bound 2 rounds; target PR ~30 min.

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
  and never redefines error copy (emits codes; renders bubble text+chips from
  frozen `ERROR_COPY`).
- **Byte-fetch**: no `fetch_report_bytes` helper is frozen/present (it lands with
  change 1). To stay parallel-safe + offline the flow takes an **injected async
  fetcher** `Callable[[str], Awaitable[bytes]]`; tests inject a fake. FLAG B: the
  signed URL is fetched server-side and discarded — never cached/logged/surfaced.
- **FLAG B (security-critical)**: `cmlLink` never enters a render block (frozen
  `FileCard` has no url field and forbids extra), never logged. Enforced + tested.
- **Filename carve-out**: keep server filename `Client_Master_List.pdf` (§2.6).
- **Password**: `password_hint=None` — [ASSUMPTION] CML PDF unprotected (spec §9
  item 12) encoded verbatim as a [CONFIRM].

## Open questions / [CONFIRM] / [GAP]
- [CONFIRM] CML PDF password status (assumed unprotected) — carried from proposal.
- [CONFIRM] `source: FINX_ANDROID` gating + generic report-generator shape — owned
  by the MIS/JWT adapter (change 1), not this flow.
- [GAP/NOTE] The engine↔flow execution binding (`FlowDefinition`, adapter-binding
  signature, filename/password/chip declarations, delivery assembly) is NOT frozen
  in contracts-foundation; only minimal `FlowSpec` is. cml.py exposes both the
  frozen `FlowSpec` surface AND clearly-named declarations
  (`DISPLAY_FILENAME`, `PASSWORD_HINT`, `FILE_FORMAT`, chip builders, `run()`) so
  the engine can drive it once its binding lands. If the engine's final binding
  differs, integration wiring is the engine/orchestrator's concern (later wave);
  this flow stays fully functional + self-tested. Flagged for the team lead.

## Progress
- [x] T1 — scaffold: tasks.md + loop.md (commit fd39e6f); empty
  `tests/flows/__init__.py` added with T3.
- [x] T2 — implement `app/flows/cml.py` (commit 6763950). Imports clean;
  `isinstance(FLOW, FlowSpec)` True; `FLOW.intent == Intent.report_cml`.
- [x] T3 — `tests/flows/test_cml.py` (commit 34c6d9a): 16 tests, all green.
  `pytest tests/flows/test_cml.py` → 16 passed.
- [ ] T4 — verify + ship

## Current task
T4 — fast verify (one fresh spec-verifier, all three lenses) → fix blocking →
rebase onto origin/main → full `uv run pytest` → push + PR.

## Verifier rounds
(pending — round 1 next)

## Metrics
- Verifier rounds used: 0
- Findings per round: —
- Escalations: 0 (engine↔flow binding GAP above noted for team lead, non-blocking)
