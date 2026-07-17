# Loop state: finx-http-adapters

Branch: `finx-http-adapters` — worktree
`/home/choice/projects/customer-support/finx-http-adapters`.
Base: main @ cfb22a1 (contracts-foundation merged; frozen surface on main).
testCommand: `pytest tests/finx_adapters/`.

## Contract / scope anchors

- Frozen (read-only, never edit): `app/finx/interfaces.py`,
  `app/finx/envelopes.py`, `app/finx/models.py`, `app/contracts/**`,
  `app/config/**`, `app/llm/client.py`, `app/main.py`,
  `app/store/migrations/**`, `pyproject.toml`, `uv.lock`.
- Owned (write): `app/finx/adapters/**`, `tests/finx_adapters/**` (+ my
  `tasks.md`/`loop.md`).
- Magic bytes are the FROZEN `ByteValidation` (`%PDF`, `PK`, min 1024) — NOT the
  proposal-prose `PK\x03\x04`. Frozen config wins.
- Credentials injected at construction (frozen methods take only `req`);
  `FinXCredentials{session_id, sso_jwt}`.

## Tasks

- [x] Task 0 — author tasks.md + scaffold loop.md, commit before implementing.
- [ ] Task 1 — errors + credentials + HTTP transport base
- [ ] Task 2 — byte-fetch helper + validation primitive
- [ ] Task 3 — .NET middleware adapter (6 endpoints)
- [ ] Task 4 — Go adapter (contract list, per-note download, brokerage)
- [ ] Task 5 — MIS adapter (CML)
- [ ] Task 6 — MF profile adapter (first-name-only PII discipline)
- [ ] Task 7 — COTI holdings adapter
- [ ] Task 8 — facade + package exports
- [ ] Task 9 — consolidated redaction/no-leak tests + doneCondition sweep

Current task: Task 1.

## Verifier rounds

(none yet)

## Open questions / carried items

- [CONFIRM] Ledger `Margin:1`=MTF and `RequestFor:1` email are unverified in the
  frozen models — implemented as-modelled; not re-litigated here.
- [CONFIRM] COTI body `accessToken` (FINX JWT) provenance unresolved — adapter
  takes it caller-supplied via `HoldingsRequest.accessToken`, does not source it.
- [GAP] Global-Detail file delivery has no endpoint — only `GetDetailedPNL`
  data; no download adapter provided (correct per spec).
- Holdings + get-profile are transport-complete but their flows are
  BLOCKED/Phase-2 respectively (correct per spec).

## Metrics

Verifier rounds used: 0. Findings per round: n/a. Escalations: 0.
