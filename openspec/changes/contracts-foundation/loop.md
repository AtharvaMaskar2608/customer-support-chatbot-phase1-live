# loop.md — contracts-foundation (Wave 0)

Worktree: /home/choice/projects/customer-support/contracts-foundation
Branch: contracts-foundation | Base: 7d9f02d (main)
testCommand: `pytest tests/contracts tests/finx`
doneCondition: package imports cleanly; full contract+parser suite passes offline
(no network, no live DB); `openspec validate --strict` passes.

## Status: VERIFIER-CONVERGED — pre-ship integration check next

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

## Verifier rounds (3 panels, all fresh-context, one per lens each)
Round 1 (on 4325e79/efcebb3): zero blocking; ~5 minor/uncertain completeness gaps → all fixed (5b1a2e6).
Round 2 (on 5b1a2e6): zero blocking; 2 minor (max-range-years, embedded-email mask) + coverage/notation → fixed (4e3399a).
Round 3 (on 4e3399a): ZERO blocking across all 3 lenses. Remaining items all uncertain/minor and
  either correct-as-designed or non-required coverage → 2 test-only hardening additions (error/Go-401
  branches); no contract change. CONVERGED (two consecutive clean fresh panels).

## Findings resolution
Round 3 items — none are confirmed divergences; dispositions:
  - Greeting/placeholder "rotate": widget-side rotation; config carries the templates. Not a divergence.
  - error / Go-401 parser branches untested: spec fixture requirement (success/no_data/auth_error) already
    met; added test-only coverage (82 passed) as hardening.
  - FileDeliveryResponse.Response str|None: correct — this model is scoped to the 3 string-returning file
    endpoints; array/object shapes modeled by BrokerageGroup/HoldingsResponseBody/GlobalPnlNewObject; the
    parser payload is Any.
  - mask-before-display / compliance-footer text: server-sourced (D10 lists config_slice contents; footer
    read from RemoteConfig.compliance_footer server-side). Downstream-owned. Not a divergence.
  - FY short↔long two functions vs "a single mapping function": idiomatic inverse pair, equivalent.
  - wire Calendar max_range_days vs flow max_range_years: layer split; disabled_ranges are the exact
    enforcement, engine converts. Not a break.

## Metrics
Verifier rounds used: 3 (cap). Findings per round: R1 ~5 (all fixed), R2 2 (fixed), R3 0 blocking.
Escalations: 0. Test suite: 82 passed offline (no network, no live DB).

## Round-1 detail
Round 1 (all minor/uncertain, none blocking; fixed in 5b1a2e6):
  - schema_migrations DDL not in 0001 file (task 8.1 literal wording) → added to 0001.
  - tracing thread-stitching + production-judge rule + configure caveat unrepresented → added
    new_thread_id/inline_judge_allowed + Span/span() + docstring caveat; llm span now recorded.
  - WhatsNew 24h-cache/red-dot not schema-supported → added whats_new_cache_hours/whats_new_red_dot.
  - forced-route tool_choice + transport-failure fallback only inline in a test → shipped
    ROUTE_TOOL_CHOICE + transport_failure_result() constants (manifest defines them).
  - typed response models missing for several endpoints → added FileDeliveryResponse (+aliases),
    HoldingsResponseBody, GetProfileResponse, DetailedPnlRow, LedgerDetailsRow, ContractNoteDownloadResponse.
  - package markers (app/__init__.py, app/store/migrations/__init__.py, tests/__init__.py) flagged
    as outside manifest → kept (required for importable tree; no overlap with other changes). Not a fix.

## Open questions / carried-forward [CONFIRM]/[GAP] items (encoded verbatim from proposal)
- MTF `Margin:1` discriminator unverified (byte-identical on no-MTF account) — LedgerPdfRequest.Margin=1 marked [CONFIRM].
- Holdings body `accessToken` (FINX-issued JWT iss:FINX) provenance unresolved — HoldingsRequest.accessToken [CONFIRM]; Holdings flow BLOCKED.
- SessionId lifetime/expiry undocumented — runtime risk only.
- Global Detail / Detailed P&L: no file-delivery endpoint [GAP]; report_global_detail + report_holding are enum values only (BLOCKED).
- Ledger-PDF email branch (RequestFor:1) [CONFIRM] (not live-tested).

## Escalations
(none yet)
