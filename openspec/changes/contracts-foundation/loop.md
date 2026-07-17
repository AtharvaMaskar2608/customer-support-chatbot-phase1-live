# loop.md — contracts-foundation (Wave 0)

Worktree: /home/choice/projects/customer-support/contracts-foundation
Branch: contracts-foundation | Base: 7d9f02d (main)
testCommand: `pytest tests/contracts tests/finx`
doneCondition: package imports cleanly; full contract+parser suite passes offline
(no network, no live DB); `openspec validate --strict` passes.

## Status: IMPLEMENTING

## Tasks (from tasks.md, in order)

- [ ] 1. Package scaffold & dependencies (1.1 pyproject+lock, 1.2 tree, 1.3 .env.example)
- [ ] 2. Wire contract (2.1 SessionContext, 2.2 envelope, 2.3 blocks, 2.4 config_slice, 2.5 schema drift)
- [ ] 3. Router contract (3.1 Intent/params/result, 3.2 precedence, 3.3 rag, 3.4 tools + drift)
- [ ] 4. FinX (4.1 envelopes, 4.2 interfaces, 4.3 models, 4.4 fixtures)
- [ ] 5. Flow-engine (5.1 state+FY helpers, 5.2 cache+registry)
- [ ] 6. Config (6.1 schema, 6.2 defaults, 6.3 db)
- [ ] 7. Tracing/errors/llm (7.1 tracing, 7.2 errors, 7.3 llm client)
- [ ] 8. Store migration (8.1 0001 + runner + TurnRecord)
- [ ] 9. Chat stub (9.1 /api/chat session-seed)
- [ ] 10. CI target (10.1 pytest green offline)

## Current task: 1 — package scaffold

## Verifier rounds
(none yet)

## Findings per round
(none yet)

## Open questions / carried-forward [CONFIRM]/[GAP] items (encoded verbatim from proposal)
- MTF `Margin:1` discriminator unverified (byte-identical on no-MTF account) — LedgerPdfRequest.Margin=1 marked [CONFIRM].
- Holdings body `accessToken` (FINX-issued JWT iss:FINX) provenance unresolved — HoldingsRequest.accessToken [CONFIRM]; Holdings flow BLOCKED.
- SessionId lifetime/expiry undocumented — runtime risk only.
- Global Detail / Detailed P&L: no file-delivery endpoint [GAP]; report_global_detail + report_holding are enum values only (BLOCKED).
- Ledger-PDF email branch (RequestFor:1) [CONFIRM] (not live-tested).

## Escalations
(none yet)
