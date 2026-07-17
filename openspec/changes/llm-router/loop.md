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
- [x] Task 4 — language detection + sticky rule (`_detect_language` Devanagari/
      Hinglish-marker/English; `_resolve_language` locks on English, writes sticky
      state back onto ctx; test_language_sticky.py green, 8 cases)
- [x] Task 5 — follow-up + escalation (`_resolve_follow_up` reads
      ctx.follow_up_count, escalates at frozen cap=2, passes model follow-up
      through below cap, never increments; test_follow_up.py green, 5 cases)
- [x] Task 6 — classifier + route() assembly (`_classify` forced route tool call
      via frozen LLMClient, RouterResult from tool_use.input; `Router` +
      module-level `route(utterance, ctx, *, client=None)`; transport/empty-block
      → transport_failure_result(); education_line deterministic; needs_confirmation
      is deterministic AY-only; test_router_assembly.py green, 5 cases)
- [x] Task 7 — fake client, recordings, goldens (`FakeLLMClient` replays recorded
      route tool_use by utterance; 13 recordings + 15 goldens spanning EN/HI/
      Hinglish/typos + precedence/AY/follow-up/sticky; conftest registers+skips
      `live` marker so bare testCommand stays offline; test_router_goldens.py +
      test_transport_failure.py + test_live_rerecord.py (@live, skipped in CI))
- [x] Task 8 — doneCondition + full-suite gate (`pytest tests/llm_router/` →
      64 passed, 1 skipped [live]; `uv run pytest` → 146 passed, 1 skipped, 0
      regressions; only filesTouched changed, no frozen surface touched)

## Verifier rounds

- Round 1 (3 fresh verifiers, lenses: spec-compliance / edge-cases / contract-surface):
  - **[blocking] FY helpers not consumed** (flagged by spec-compliance + contract-surface):
    FY normalization re-implemented locally instead of using the frozen
    `app.contracts.flow` helpers the manifest declares consumed (`currentFY`,
    `supportedFYs`) and Task 3 mandates. → FIXED: `parse_fy_or_ay` now normalizes
    via `fy_short_to_long`, and relative FY references ("this/current year",
    "last year", "year before last") resolve via `current_fy` / `supported_fys`
    (Apr-1 rollover stays in the frozen helper). `today` injected for determinism.
  - **[minor] `-m live` opt-in** (spec-compliance): proposal specifies `pytest -m
    live` as the live opt-in but the conftest only honored `JINI_RUN_LIVE`. → FIXED:
    conftest now also runs live when `-m live` is selected; bare testCommand still
    skips (verified: `-m live` selects it, bare run skips).
  - **[minor] typo few-shot missing** (spec-compliance): `few_shots.json` lacked a
    typos example. → FIXED: added two typo few-shots + test assertion.
  - **[uncertain] `_classify` ctx unused** (spec-compliance): `ctx.history` is
    refs-only in the frozen contract (no message text), so nothing to feed the
    model; all ctx-derived behaviour is deterministic post-processing. → clarifying
    comment added; signature matches the spec'd `_classify(utterance, ctx)`. No
    behaviour change.
  - **[dismissed] per-turn LLMClient construction** (edge-cases lens raised then
    dismissed): lazy client, spec'd stateless pure function, `Router` provides the
    reuse hook. No action.
  - edge-cases lens found no functional defects.
  - Post-fix: `pytest tests/llm_router/` 67 passed / 1 skipped; `uv run pytest`
    149 passed / 1 skipped, 0 regressions.
- Round 2 (3 fresh verifiers, none had seen the code):
  - **contract-surface: NO divergences** (frozen FY helpers now consumed; all
    manifest-declared contracts consumed; no frozen file edited).
  - **edge-cases** (genuine deterministic-layer bugs → FIXED):
    - **[minor] `_detect_language` false-Hinglish**: markers "do"/"de"/"ka"/"ki"
      collide with English ("how do i…" → hinglish). → FIXED: pruned colliding
      short tokens; added English-stays-English tests. (Was masked in goldens
      because the model supplies detected_language; only the fallback path was hit.)
    - **[minor] stray "ay" flips FY→AY**: "ay yes … 2024-25" read as Assessment
      Year. → FIXED: AY detection now proximity-scoped (qualifier must directly
      precede the year) via `_AY_RANGE_RE`/`_AY_SINGLE_RE`.
    - **[minor] valid FY after a non-consecutive ISO fragment dropped**: only the
      first range match was tested. → FIXED: `finditer` scans for the first
      consecutive range.
    - [uncertain] `except Exception` also catches model_validate failures →
      unreachable under strict tool use; graceful fallback is safer product
      behaviour than crashing. No change (documented).
  - **spec-compliance** (all non-blocking, no change needed):
    - [uncertain] date_range not deterministically parsed → tasks.md Task 3
      explicitly sanctions model pass-through; date parsing is out of the FY/AY
      deterministic scope. No change.
    - [minor] live opt-in also honors JINI_RUN_LIVE beyond `-m live` → additive
      superset; `-m live` works and bare testCommand stays offline. Kept as a
      convenience.
    - [minor] filesTouched omits tasks.md/loop.md → CLAUDE.md + assignment
      explicitly authorize authoring those proposal-dir files. Not a code-surface
      violation.
    - [spec-suspect] escalate-at-cap fires even for an unambiguous turn → this is
      faithful to the proposal ("at the cap … signals escalation instead; the
      router respects it"). Verifier could not renegotiate the spec; no divergence.
  - Post-fix: `pytest tests/llm_router/` 70 passed / 1 skipped; `uv run pytest`
    152 passed / 1 skipped, 0 regressions.
- Round 3 (3 fresh verifiers, none had seen the code):
  - **contract-surface: NO divergences** (re-confirmed clean).
  - **edge-cases**:
    - **[BLOCKING] AY qualifier lacked a leading word boundary** — words ending in
      "-ay" adjacent to a year ("may 2024-25", "display 2024-25", "friday 2024")
      were misread as Assessment Years (FY shifted −1yr + spurious confirmation).
      This was introduced by the round-2 proximity fix. → FIXED: `_AY_QUALIFIER`
      now has `(?<![a-z])`. Verified: "may 2024-25" → FY 2024-2025 (not AY); genuine
      "AY 2025-26" still → 2024-2025 + confirmation.
    - **[minor] singular precedence tokens missed plurals** ("capital gains",
      "contract notes") → FIXED: `_token_matches` tolerates an optional trailing
      "s". Verified.
    - **[minor] `_normalize_fy` dropped the AY flag** for a model-carried AY →
      FIXED: `_extract_params` re-parses the model fy and keeps `is_ay`.
    - **[minor/uncertain] FY injected into non-tax (date-range) flows** vs the
      few-shot exemplar → FIXED: FY parsing gated to `TAX_FLOW_INTENTS` (fy is a
      Tax-flow-only tool parameter). Removed now-unused `_normalize_fy`.
    - [minor/test] vacuous "cg" boundary assertion → FIXED (uses "mcgraw").
  - **spec-compliance** (all non-blocking, no change):
    - [spec-suspect] proposal bullet-2 prose says the precedence table lives in
      `app/llm/prompts/`, but Gate-1 reconciliation froze `PRECEDENCE_TOKENS` into
      contracts-foundation and Task 2 mandates using it. Code follows the frozen
      contract; the prose is stale. No divergence from the reconciled contract.
    - [minor] live "skipped" vs "deselected" wording — offline guarantee met.
    - [minor/uncertain] segment "cash"/delivery "here" not in the deterministic
      fallback tables — the model (prompted on them) is the primary extractor; the
      tables only augment. Left as-is (augmentation completeness, not a spec breach).
  - Post-fix: `pytest tests/llm_router/` 79 passed / 1 skipped; `uv run pytest`
    161 passed / 1 skipped, 0 regressions. Blocking + all real minors resolved.

## Convergence status / ESCALATION

3 verifier panels used (the protocol cap). Trend converged: findings were real,
distinct, and decreasing (R1: 1 blocking; R2: 0 blocking, 3 minor; R3: 1 blocking
[self-introduced in R2] + minors), each fixed and verified with new tests; no
finding recurred across panels; contract-surface was clean in R2 and R3. But the
3rd panel still surfaced a blocking item, so I have NOT obtained a clean fresh
panel within the 3-panel budget → escalating to the team lead per protocol
("not converged after 3 → stop and escalate") for a decision: authorize one
confirmation panel on the R3-fixed head, or accept. Not shipping without a clean
panel or team-lead direction.

## Open questions / escalations

- none. Frozen `PRECEDENCE_TOKENS` order is authoritative; the
  generalization carve-out (keep MTF/CG/Tax-P&L over their base token) is an
  implementation guard, not a spec change — noted here for the verifier panel.

## Metrics

- verifier rounds used: 0
- findings per round: n/a
- escalations: 0
