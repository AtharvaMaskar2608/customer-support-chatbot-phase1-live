# loop.md — contracts-foundation (Wave 0)

Worktree: /home/choice/projects/customer-support/contracts-foundation
Branch: contracts-foundation | Base: 7d9f02d (main)
testCommand: `pytest tests/contracts tests/finx`
doneCondition: package imports cleanly; full contract+parser suite passes offline
(no network, no live DB); `openspec validate --strict` passes.

## Status: IMPLEMENTATION COMPLETE — awaiting verifier panel

Implementation/commit order is dependency-first (leaf contract modules before
consumers), so every commit is importable and green. All tasks.md sections are
completed; only the commit sequence differs from the numeric order.

## Tasks (from tasks.md, all complete)

- [x] 1. Package scaffold & dependencies — commit 9388fc6
- [x] 2. Wire contract — commit f22bfb7
- [x] 3. Router contract (rag — ef72bc0; tools + drift — b8074cd)
- [x] 4. FinX envelopes/interfaces/models/fixtures — commit 31ebd94
- [x] 5. Flow-engine contract — commit cc1889a
- [x] 6. Config (schema/defaults/db) — commit 196ef3b
- [x] 7. Tracing (7.1) + LLM client (7.3) — commit f100393; error taxonomy (7.2) — commit 8bdf177
- [x] 8. Store migration + TurnRecord — commit bcd2bca
- [x] 9. Chat stub — commit 4325e79
- [x] 10. CI target — full offline suite green (71 passed)

## doneCondition verification
- All modules import cleanly (app + every contract/finx/llm/config/store module).
- `pytest tests/contracts tests/finx` = 71 passed, offline (no network, no live DB).
- `openspec validate contracts-foundation --strict` = valid (exit 0).
- Migration runner idempotent on re-run (dry-run parse). Both generated JSON
  Schemas (chat_wire, tools) have passing drift tests.

## Verifier rounds
Round 1: pending (3 fresh spec-verifiers — spec-compliance, edge-cases, contract-surface).

## Findings per round
Round 1: pending

## Open questions / carried-forward [CONFIRM]/[GAP] items (encoded verbatim from proposal)
- MTF `Margin:1` discriminator unverified (byte-identical on no-MTF account) — LedgerPdfRequest.Margin=1 marked [CONFIRM].
- Holdings body `accessToken` (FINX-issued JWT iss:FINX) provenance unresolved — HoldingsRequest.accessToken [CONFIRM]; Holdings flow BLOCKED.
- SessionId lifetime/expiry undocumented — runtime risk only.
- Global Detail / Detailed P&L: no file-delivery endpoint [GAP]; report_global_detail + report_holding are enum values only (BLOCKED).
- Ledger-PDF email branch (RequestFor:1) [CONFIRM] (not live-tested).

## Escalations
(none yet)
