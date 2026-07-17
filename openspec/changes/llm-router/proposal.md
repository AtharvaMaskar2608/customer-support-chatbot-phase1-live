# Proposal: llm-router

## Why

The core architecture (`docs/technical/02_technical_spec.md` §2.2) is a **deterministic flow engine gated by a thin LLM router**. The router is the single entry point that turns a free-text utterance into a typed decision — which flow/RAG/ticket to run, and which parameters the user already supplied — so the flow engine never has to guess and the LLM never improvises fulfilment. `contracts-foundation` freezes the router's I/O surface (`Intent`, `ExtractedParams`, `RouterResult`) but ships **no behaviour**: nothing classifies utterances, extracts params, applies the §2.5 intent-precedence rules, detects language, or generates follow-ups yet. Without this change, the orchestrator (change 5) has an interface but no brain behind it, and every downstream flow is unreachable from natural language.

This change implements that brain — and only that brain. It is a pure function over `(utterance, ConversationContext)`: LLM classification + deterministic post-processing, no FinX calls, no DB reads, no stepper control.

## What Changes

- **Intent classification** — one Claude call (via the frozen `app/llm/client.py`, `claude-sonnet-5` pinned, `claude-haiku-4-5-20251001` toggle) with a **forced native tool call**: `tools=[route]` (declared `strict: true`), `tool_choice={"type":"tool","name":"route","disable_parallel_tool_use":true}`, where the `route` tool's `input_schema` is the frozen generated schema for `RouterResult` (`contracts-foundation` `app/contracts/tools.py`, mirrored to `tools.schema.json`). `RouterResult` materializes directly from the API-validated `tool_use.input` block — no prompt-then-parse-JSON. The prompt carries the full `Intent` taxonomy (11 report flows + RAG + ticket + smalltalk/fallback).
- **Deterministic intent-precedence layer** (§2.5) applied *after* the LLM proposes candidates, so precedence is testable and never left to model whim: `"tax"` beats `"p&l"`; `"capital gain"`/`"CG"` → `Tax`; bare `"P&L"` → `P&L`; `"holding statement"` → `Holding` (not `Ledger`). Encoded as a keyword→forced-intent rule table in `app/llm/prompts/`, resolved in `router.py`.
- **Parameter extraction from free text only** — FY (with `FY 2025-26` ↔ `"2025-2026"` normalization via the frozen `currentFY`/`supportedFYs` helpers), date ranges, segment, format (PDF/Excel), delivery (download/email). Params absent from the utterance are left unset for the flow engine's stepper to collect — the router does **not** drive the stepper.
- **AY→FY conversion flagged for confirmation** — when the user gives an Assessment Year, the router maps AY→FY and sets `needs_confirmation` rather than assuming (§2.5).
- **Follow-up generation only when genuinely ambiguous** — at most **one** follow-up question per turn, emitted only when confidence is low or a required disambiguation is missing. The router reads the running follow-up count from `ConversationContext` and, at the remote-config `follow_up_cap` (2), stops proposing follow-ups and signals escalation instead. Cross-turn cap enforcement itself lives in the orchestrator; the router respects it.
- **Language detection + sticky-language** — detect English/Hindi/Hinglish; apply the sticky rule (English once → English thereafter, §8.5) by reading the prior-language signal from `ConversationContext` and forcing English when it is set. Emits `detected_language` on `RouterResult`; the sticky-language state itself persists on `ConversationContext` across turns.
- **Externalized prompts** — system prompt, intent taxonomy + precedence table, param-extraction schema, few-shot examples (English/Hindi/Hinglish/typos), and follow-up guidance all live under `app/llm/prompts/` as versioned files loaded at runtime, per the §2.2 "prompts externalized, not in code" rule.

Out of scope: the orchestration loop, the 10-message cap, cache/byte handling, and any FinX/RAG execution — the router only classifies and extracts.

## Capabilities

### New Capabilities

- `llm-router`: the thin LLM router — utterance → `RouterResult` (intent classification, free-text param extraction, deterministic precedence resolution, AY→FY confirmation flagging, one-shot follow-up generation, language detection + sticky-language).

### Modified Capabilities

None — consumes the frozen `router-contract` from `contracts-foundation`; does not modify it.

## Impact

- **New code**: `app/llm/router.py` + `app/llm/prompts/**`; tests under `tests/llm_router/**`.
- **Runtime**: one Claude call per turn; no FinX, no DB, no network beyond the Claude client.
- **Downstream**: unblocks the conversation-orchestrator (change 5), which builds against this interface (or a fake) and dispatches on `RouterResult.intent`.

## Files touched

Exclusive ownership (ownership map row 3), nothing outside it:

- `app/llm/router.py` — the router implementation (`route`, precedence resolver, param extractors, language/sticky logic).
- `app/llm/prompts/**` — externalized system prompt, intent-precedence rule table, param-extraction schema, few-shot examples, follow-up guidance.
- `tests/llm_router/**` — golden fixtures, recordings, and the fake LLM client.

**Untouched**: `app/llm/client.py` (owned by `contracts-foundation`, imported read-only), lockfiles, migrations, and all root config are **not** modified by this change.

## Contracts & API structure

All types below are the **frozen `router-contract`** from `contracts-foundation` (`app/contracts/`); this change imports them and implements behaviour only.

- `route(utterance: str, ctx: ConversationContext) -> RouterResult`
  - **Input**: raw user utterance; `ConversationContext` = conversation history + sticky-language signal + running follow-up count + session context (`userId`/`sessionId`/`platform`/`page` from the URL-param bootstrap).
  - **Output**: `RouterResult` (frozen `router-contract`, full field set per Dependencies below) — `intent: Intent`, `extracted_params: ExtractedParams` (FY, date range, segment, format, delivery — only fields present in the utterance), `needs_confirmation: bool` (AY→FY), `follow_up_question: str | None` (≤1; non-null only when a genuine ambiguity remains), `detected_language`, `escalate: bool`, `education_line`. (Sticky-language state lives on `ConversationContext`, not `RouterResult`.)
  - **Errors**: never raises to the caller for classification uncertainty — low confidence surfaces as a `follow_up_question` or `escalate`, not an exception. Schema conformance is enforced API-side by the forced tool call, so there is no parse/repair step; only an API/transport error returns a fallback `RouterResult(intent=FALLBACK, escalate=True)`. No user-facing copy is produced here (that is the orchestrator/error-taxonomy layer).
- Internal (private to `router.py`, not part of the frozen contract):
  - `_classify(utterance, ctx) -> RawClassification` — the single forced-tool-call Claude request; reads the `RouterResult` fields from the returned `tool_use.input` block (no JSON parsing of free text).
  - `_resolve_precedence(candidates) -> Intent` — deterministic §2.5 rule table.
  - `_extract_params(utterance, intent) -> ExtractedParams` — FY normalization (`currentFY`/`supportedFYs` from `flow-engine-contract`), AY→FY, date/segment/format/delivery.
  - `_detect_language(utterance, ctx) -> (Language, sticky: bool)`.
- **No FinX/Freshdesk endpoints** are called by this change; no entry from `03_finx_api_reference.md` applies.

## Dependencies & contracts consumed

**Consumed from `contracts-foundation` (must land in main first):**
- `router-contract`: `Intent`, `ExtractedParams`, `RouterResult`, and the generated `route`-tool `input_schema` for `RouterResult` (`app/contracts/tools.py`).
- `llm-client`: `app/llm/client.py` (pinned `claude-sonnet-5` + Haiku toggle).
- `flow-engine-contract`: `currentFY`, `supportedFYs`, the `FY 2025-26 ↔ "2025-2026"` mapping helper (for FY normalization/validation).
- `remote-config`: `follow_up_cap` (=2), greeting/language config as needed.

**RESOLVED — folded into `contracts-foundation` (2026-07-17 Gate-1 reconciliation).** Both gaps this proposal originally surfaced are closed in the updated contracts-foundation artifacts:
- `ConversationContext` is a frozen contracts type (bootstrap fields + history refs + `turn_number` + `follow_up_count` + sticky-language state), spec'd under `router-contract`.
- `RouterResult` is frozen with the full field set: `intent`, `extracted_params`, `needs_confirmation`, `follow_up_question`, `detected_language`, `escalate`, `education_line` — and its generated schema is the `route` tool's `input_schema` in `app/contracts/tools.py`.

**Parallelism**: depends only on `contracts-foundation` (row 3, "depends on 0"). No file overlap with `finx-http-adapters`, `flow-engine-runtime`, or `rag-service`; runs fully in parallel once contracts land. The orchestrator (5) depends on this change's **interface only** and can build against a fake.

## Done condition & test command

**Done when**: `route(utterance, ctx)` produces the correct `RouterResult` for the golden utterance set spanning English/Hindi/Hinglish/typos, with the §2.5 precedence rules, AY→FY confirmation, one-shot follow-ups, and sticky-language all covered — **with no live LLM call in CI**.

**No-live-LLM strategy (chosen): record/replay at the client boundary.** Tests inject a `FakeLLMClient` into `router.py` that replays pre-recorded Claude **`tool_use` blocks** (not text completions) keyed by utterance (recordings committed under `tests/llm_router/recordings/`). Golden fixtures (`tests/llm_router/goldens/*.json`) map `utterance → expected RouterResult`. The deterministic layers (precedence resolver, FY normalization, language stickiness) are also unit-tested directly with no LLM at all. A manual/nightly `pytest -m live` opt-in re-records against the real client; `-m live` is deselected in CI.

**Test command**: `pytest tests/llm_router/` (green; fixture/recording-based, no network).
