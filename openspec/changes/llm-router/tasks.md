# Tasks: llm-router

Ordered, verifiable tasks. Every task maps to the proposal (proposal.md is the
contract; these tasks never expand scope). Each is committed on its own with
`loop.md` updated in the same commit. All work stays inside `filesTouched`:
`app/llm/router.py`, `app/llm/prompts/**`, `tests/llm_router/**` (plus authored
`tasks.md` / `loop.md`). Frozen surfaces are imported read-only, never edited.

The router is a **pure function over `(utterance, ConversationContext)`**: one
forced native `route` tool call (`ROUTE_TOOL_CHOICE`) + deterministic
post-processing. No FinX, no DB, no stepper control. CI is offline record/replay
— no live LLM call.

---

## Task 1 — Externalized prompts + loader (`app/llm/prompts/**`)

Create the versioned prompt assets loaded at runtime (proposal §What Changes
"Externalized prompts", §2.2 "prompts externalized, not in code"):

- `system.md` — router system prompt (role, forced-tool contract, output rules).
- `intent_taxonomy.md` — the full 16-value `Intent` taxonomy (11 report + 5
  non-report, incl. the two BLOCKED intents) + the §2.5 precedence guidance.
- `param_extraction.md` — FY/AY, date-range, segment, format, delivery guidance.
- `follow_up.md` — one-shot follow-up + escalation guidance.
- `few_shots.json` — few-shot examples spanning English/Hindi/Hinglish/typos as
  `{utterance, route_input}` pairs.
- `education_lines.json` — externalized CG / Tax-P&L education-line copy.
- `__init__.py` — a loader that reads these files at runtime and assembles the
  system prompt (no prompt text hardcoded in `router.py`).

**Done:** `from app.llm.prompts import load_system_prompt, few_shots,
education_line` all import; `load_system_prompt()` returns a non-empty string
containing every `Intent` value; `education_line(Intent.report_capital_gain)`
and `education_line(Intent.report_tax_pnl)` return non-empty strings and every
other intent returns `None`; prompt files exist on disk (loaded, not inlined).

## Task 2 — Deterministic precedence resolver (`app/llm/router.py`)

Implement `_resolve_precedence(utterance, model_intent) -> Intent` using the
FROZEN `PRECEDENCE_TOKENS` from `app.contracts.router` (§2.5): first token in
frozen order that word-boundary-matches the utterance wins; override applies
only when `model_intent` is a report intent; a more-specific model intent is
kept over its generalization (`report_ledger ⊃ report_mtf_ledger`;
`report_tax ⊃ report_capital_gain, report_tax_pnl`).

**Done:** `tests/llm_router/test_precedence.py` (no LLM) is green: "tax report or
p&l" → `report_tax`; "capital gain report" → `report_capital_gain`; "holding
statement" → `report_holding` (not `report_ledger`); bare "p&l"/"pnl" →
`report_pnl`; "mtf ledger" keeps `report_mtf_ledger`; "tax p&l" keeps
`report_tax_pnl`; a `rag_qa`/`smalltalk_fallback` model intent is never forced
to a report; no precedence token → model intent unchanged.

## Task 3 — Deterministic FY/AY normalization (`app/llm/router.py`)

Implement `parse_fy_or_ay(utterance) -> (fy_long | None, is_ay)` and
`_extract_params(utterance, intent, model_params) -> (ExtractedParams,
needs_confirmation)` using the FROZEN `fy_short_to_long`/`current_fy`/
`supported_fys` helpers from `app.contracts.flow`: normalize `FY 2025-26` ↔
`"2025-2026"`; AY→FY maps AY start year S → FY start year S-1 and sets
`needs_confirmation`; deterministic FY is authoritative over the model's;
segment/format/delivery augment only when the model left them unset;
`date_range` passes through from the model.

**Done:** `tests/llm_router/test_fy_normalization.py` (no LLM) is green: "FY
2025-26" → `"2025-2026"`, `needs_confirmation=False`; "AY 2025-26" → `"2024-2025"`,
`needs_confirmation=True`; "2025-2026" round-trips; no FY/AY in utterance and no
model FY → `fy is None`.

## Task 4 — Deterministic language detection + sticky rule (`app/llm/router.py`)

Implement `_detect_language(utterance) -> Language` (Devanagari → hindi;
romanized-Hindi markers → hinglish; else english) and
`_resolve_language(utterance, ctx, model_language) -> Language` applying §8.5:
once English is seen the language locks to English thereafter; Hindi/Hinglish do
not lock; the sticky state (`detected_language` + `language_locked`) is written
back onto `ConversationContext` while `RouterResult.detected_language` carries
this turn's language.

**Done:** `tests/llm_router/test_language_sticky.py` (no LLM) is green: locked ctx
→ english regardless of a Hindi utterance; english utterance locks the ctx; a
Hindi utterance on an unlocked ctx stays hindi and does not lock; a Devanagari
utterance detects hindi; Hinglish detects hinglish.

## Task 5 — Follow-up + escalation resolution (`app/llm/router.py`)

Implement `_resolve_follow_up(ctx, model_follow_up, model_escalate) ->
(follow_up_question | None, escalate)`: at most one follow-up per turn; the
router READS `ctx.follow_up_count` and, at the remote-config `follow_up_cap`
(=2), emits no follow-up and sets `escalate=True`; below the cap it passes the
model's single follow-up through; the model's own `escalate` is respected. The
router never increments the cross-turn count (orchestrator-owned).

**Done:** `tests/llm_router/test_follow_up.py` (no LLM) is green: `follow_up_count
< cap` with a model follow-up → that follow-up, `escalate=False`;
`follow_up_count == cap` → `follow_up_question is None`, `escalate=True`; model
`escalate=True` below cap → `escalate=True`.

## Task 6 — Classifier + `route()` assembly (`app/llm/router.py`)

Implement `_classify(utterance, ctx, client) -> RouterResult` — ONE forced
`route` tool call via the frozen `LLMClient` with `tools=[TOOLS_BY_NAME["route"]]`
and `tool_choice=ROUTE_TOOL_CHOICE`; `RouterResult` materializes from the
API-validated `tool_use.input` (no JSON parsing of free text); any API/transport
error returns `transport_failure_result()`. Assemble `route(utterance, ctx, *,
client=None) -> RouterResult` wiring precedence → params/confirmation → language
→ follow-up/escalate → education line, plus a `Router` class for client
injection.

**Done:** `route` issues exactly one `client.complete(...)` call carrying
`tool_choice=ROUTE_TOOL_CHOICE` and the frozen `route` tool; a raising client →
`transport_failure_result()` (`smalltalk_fallback`, `escalate=True`);
`education_line` is set only for CG / Tax-P&L final intents.

## Task 7 — Fake client, recordings, goldens (`tests/llm_router/**`)

Add `FakeLLMClient` (replays recorded `tool_use` blocks keyed by utterance),
`recordings/route_recordings.json`, `goldens/goldens.json`
(utterance → expected `RouterResult`) spanning English/Hindi/Hinglish/typos, the
`conftest.py` that registers + deselects the `live` marker so bare `pytest
tests/llm_router/` stays offline, and `test_router_goldens.py` replaying every
golden end-to-end. Add `test_transport_failure.py` and a `@pytest.mark.live`
opt-in re-record test that is skipped in CI.

**Done:** `pytest tests/llm_router/` is green with NO network; every golden's
final `RouterResult` matches; `pytest -m live tests/llm_router/` is the only way
the live re-record test runs (deselected by default).

## Task 8 — doneCondition + full-suite gate

Confirm `pytest tests/llm_router/` (testCommand) is green and the whole
behaviour of the doneCondition is covered (English/Hindi/Hinglish/typos golden
set + §2.5 precedence + AY→FY confirmation + one-shot follow-ups +
sticky-language, no live LLM in CI). Run the full `uv run pytest` to confirm no
regression against the frozen contracts.

**Done:** `pytest tests/llm_router/` exits 0; `uv run pytest` exits 0 (no
regressions); loop.md records the metrics.
