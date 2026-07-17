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

Current task: round-1 panel done (1 fix applied); spawning round-2 fresh panel.

## Verifier rounds

### Round 1 (3 fresh verifiers: spec-compliance / edge-cases / contract-surface)

Zero HARD divergences. All three panels found the endpoint/auth/envelope/field-trap
mapping, the frozen-interface binding, the filesTouched boundary (only
app/finx/adapters/** + tests/finx_adapters/** + this change's tasks.md/loop.md),
and the contract surface CLEAN. Items raised were all low/uncertain/spec-suspect:

- **FIXED (edge #2): `download_contract_note` had no non-200/non-401 guard** — an
  error body starting with `%PDF` above the floor could pass. Added
  `status != 200 -> FinXFetchError`, mirroring `fetch_report_bytes`. +1 test.
- **NO CHANGE (spec-suspect, raised x2): xlsx magic** — proposal prose says
  `PK\x03\x04`, but the FROZEN `ByteValidation.excel_magic = b"PK"` and the
  doneCondition also says "PK". Code correctly consumes the frozen config
  (frozen wins over prose). Non-blocking proposal-prose nit; surfaced to lead.
- **NO CHANGE (uncertain, raised x2): PNL/Ledger/Tax email-confirmation returned
  unmasked** — masking is a "before any display" render concern; this change is
  explicitly "no rendering". Adapter never logs the payload (verified). CARRIED
  FORWARD as a mandatory handoff: the P&L/Ledger/Tax FLOW changes MUST mask the
  registered email (`san***@…`) before display (frozen FileDeliveryResponse
  docstring + EC-12 `{masked_email}`).
- **NO CHANGE: MIS body-shape auth branch** (frozen parser, read-only; only
  reachable on HTTP!=401 with body statusCode:401 — a defensible auth signal).
- **NO CHANGE: Go true-empty-204** — captured fixture always carries a JSON body
  (StatusCode:204 in body); matches the frozen contract. Speculative empty-204
  handling would be over-engineering.
- **NO CHANGE: `sso_jwt=None` sends empty auth header** — degrades to
  401->FinXAuthError; proposal requires no early guard; orchestrator owns
  supplying JWT-auth credentials.
- **NO CHANGE: `fetch_report_bytes` is `async`** — every frozen FinX method is
  `async def`; the engine awaits it. Intended.

Findings requiring a code change: 1 (download guard). Full suite: 73 passed.

## Open questions / carried items

- [CONFIRM] Ledger `Margin:1`=MTF and `RequestFor:1` email are unverified in the
  frozen models — implemented as-modelled; not re-litigated here.
- [CONFIRM] COTI body `accessToken` (FINX JWT) provenance unresolved — adapter
  takes it caller-supplied via `HoldingsRequest.accessToken`, does not source it.
- [GAP] Global-Detail file delivery has no endpoint — only `GetDetailedPNL`
  data; no download adapter provided (correct per spec).
- Holdings + get-profile are transport-complete but their flows are
  BLOCKED/Phase-2 respectively (correct per spec).
- **HANDOFF to flow-pnl / flow-ledger-mtf / flow-tax-report:** the email-delivery
  (`RequestFor` email) confirmation payload contains the uppercased registered
  email; the FLOW must mask it (`san***@…`) before display. The adapter returns
  it raw (server-side, never logged) by design — masking is a render concern.

## Metrics

Verifier rounds used: 0. Findings per round: n/a. Escalations: 0.
