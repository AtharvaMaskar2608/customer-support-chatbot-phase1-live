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
- [x] Task 1 — errors + credentials + HTTP transport base (14 tests green:
      retry-once, 5xx→FinXTransportError, timeout/network→FinXTimeoutError,
      no-retry on 401/business-fail, non-JSON→FinXTransportError, log redaction)
- [x] Task 2 — byte-fetch helper + validation primitive (14 tests green:
      %PDF/PK accept above floor, short/empty/wrong-magic/404/5xx→FinXFetchError,
      timeout→FinXTimeoutError, signed URL never logged; frozen ByteValidation used)
- [x] Task 3 — .NET middleware adapter (6 endpoints) (13 tests green:
      URL+SessionId header/body, RequestFor 0/2 traps, GROUP1 vs Group1,
      LoginId JIFFY/client-code, UserId neuron, With_Exp truthy, Data-not-found
      vs Data-not-available no-data, 401->FinXAuthError, URL never logged)
- [x] Task 4 — Go adapter (contract list / download / brokerage) (10 tests
      green: SessionId-header-only + no body SessionId (FLAG A), file_id keying,
      204 no-data, Session-prefixed download returning validated bytes, hybrid
      brokerage via .NET parser w/ desc verbatim, file_id never logged).
      Refactor: single auth-mapping site raise_for_auth() in base.py; dotnet re-uses it.
- [ ] Task 5 — MIS adapter (CML)
- [ ] Task 6 — MF profile adapter (first-name-only PII discipline)
- [ ] Task 7 — COTI holdings adapter
- [ ] Task 8 — facade + package exports
- [ ] Task 9 — consolidated redaction/no-leak tests + doneCondition sweep

Current task: Task 5.

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
