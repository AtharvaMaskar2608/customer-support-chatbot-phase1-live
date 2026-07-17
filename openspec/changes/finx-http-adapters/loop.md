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
- [x] Task 5 — MIS adapter (CML) (4 tests green: three MIS headers
      authType/authorization-SSO-JWT/source, camelCase body, cmlLink at
      body.cmlLink, never handed SessionId, HTTP-401->FinXAuthError, cmlLink
      never logged)
- [x] Task 6 — MF profile adapter, first-name-only PII discipline (5 tests
      green: SSO-JWT auth + {InvCode} body; success reduced to first name only;
      PAN/email/mobile/DOB/bank never in returned envelope or logs; error
      discards payload; 401->FinXAuthError)
- [x] Task 7 — COTI holdings adapter (4 tests green: Session-prefixed auth +
      ssotoken SSO-JWT header + body accessToken FINX-JWT; lDictHoldingData
      keyed by ISIN; SessionId/both JWTs never logged; 401->FinXAuthError;
      in-band Fail returned not raised)
- [x] Task 8 — facade + package exports (6 tests green: FinXClientImpl
      satisfies FinXClient Protocol, each backend attr satisfies its Protocol,
      routes end-to-end, all public names exported)
- [x] Task 9 — consolidated redaction/no-leak sweep (2 tests green: facade-wide
      sweep asserts no URL/file_id/signed-query/SessionId/JWT/cmlLink/PII in any
      log sink while endpoint diagnostics still logged; profile PII never in payload).
      Full testCommand: 72 passed. Full repo suite: 154 passed.

Current task: all 9 tasks done + testCommand green. Next: fresh verifier panel (round 1).

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
