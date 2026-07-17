# Loop state: llm-router

Worktree: `/home/choice/projects/customer-support/llm-router`
Branch: `llm-router` (forked from main @ cfb22a1 — contracts-foundation merged).
testCommand: `pytest tests/llm_router/`
doneCondition: golden set (EN/HI/Hinglish/typos) + §2.5 precedence + AY→FY
confirmation + one-shot follow-ups + sticky-language, no live LLM in CI.

## Contract anchors (read from frozen surfaces — never edited)

- `app/contracts/router.py`: `Intent` (16), `ExtractedParams`, `RouterResult`,
  `ConversationContext` (has `follow_up_count`, `detected_language`,
  `language_locked`), `PRECEDENCE_TOKENS`, `ROUTE_TOOL_CHOICE`,
  `transport_failure_result()`, `BLOCKED_INTENTS`, `TAX_FLOW_INTENTS`,
  `EDUCATION_LINE_INTENTS`.
- `app/contracts/tools.py`: `TOOLS_BY_NAME["route"]` (input_schema = RouterResult
  strict schema), `ROUTE_TOOL_NAME`.
- `app/llm/client.py`: `LLMClient.complete(messages, system, tools, tool_choice)`
  → `LLMResponse` (`.tool_use[i].input`). Pinned `claude-sonnet-5` + Haiku.
- `app/contracts/flow.py`: `current_fy`, `supported_fys`, `fy_short_to_long`,
  `fy_long_to_short` (FY helpers, implemented).
- `app/config/schema.py` / `defaults.py`: `Limits.follow_up_cap` (=2).

## Design decisions (locked, from proposal + §2.2/§2.5/§8.5)

- Routing = ONE forced native `route` tool call; RouterResult from
  `tool_use.input`; no prompt-then-parse-JSON. Transport error only →
  `transport_failure_result()`.
- Precedence = deterministic override using frozen `PRECEDENCE_TOKENS`, applied
  after the model proposes a single intent. Overrides only report intents;
  keeps a more-specific model intent over its generalization (ledger⊃mtf_ledger;
  tax⊃capital_gain,tax_pnl) so MTF / CG / Tax-P&L survive.
- FY/AY normalization deterministic + authoritative; AY start S → FY start S-1,
  sets `needs_confirmation`.
- Sticky-language: English locks; state written back onto `ConversationContext`.
- Follow-up: ≤1/turn; router READS `follow_up_count`, at cap (2) → escalate; the
  cross-turn increment is orchestrator-owned.
- Prompts externalized under `app/llm/prompts/**`, loaded at runtime.
- CI offline: `FakeLLMClient` replays recorded `tool_use` blocks; goldens pin
  final RouterResult; deterministic layers unit-tested with no LLM.

## Tasks

- [x] Task 0 — author tasks.md + scaffold loop.md (this commit)
- [x] Task 1 — externalized prompts + loader (system/taxonomy/param/follow-up
      .md + few_shots.json + education_lines.json + loader; test_prompts.py green,
      system prompt names all 16 intents, education lines only for CG/Tax-P&L)
- [x] Task 2 — precedence resolver (`_resolve_precedence` on frozen
      PRECEDENCE_TOKENS; word-boundary token match; report-only override +
      generalization carve-out; test_precedence.py green, 16 cases)
- [x] Task 3 — FY/AY normalization (`parse_fy_or_ay` + `_extract_params`;
      consecutive-year guard rejects ISO date fragments; AY start S → FY S-1 +
      needs_confirmation; segment/format/delivery augment only unset fields;
      non-report intents no-op; test_fy_normalization.py green, 12 cases)
- [ ] Task 4 — language detection + sticky rule
- [ ] Task 5 — follow-up + escalation
- [ ] Task 6 — classifier + route() assembly
- [ ] Task 7 — fake client, recordings, goldens
- [ ] Task 8 — doneCondition + full-suite gate

## Verifier rounds

- none yet.

## Open questions / escalations

- none. Frozen `PRECEDENCE_TOKENS` order is authoritative; the
  generalization carve-out (keep MTF/CG/Tax-P&L over their base token) is an
  implementation guard, not a spec change — noted here for the verifier panel.

## Metrics

- verifier rounds used: 0
- findings per round: n/a
- escalations: 0
