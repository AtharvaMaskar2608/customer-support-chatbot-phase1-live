# Proposal: flow-engine-runtime

## Why

The core design (`02_technical_spec.md` §2.2) is a **deterministic flow engine
gated by a thin LLM router**: once intent is known, "a hardcoded state machine
drives fulfilment … the LLM never improvises the fulfilment path." `contracts-foundation`
freezes the flow-engine-contract types (`FlowState`, `Step`, transition types,
per-flow date-window config, FY helpers, byte-validation + 15-min-cache semantics
as typed config) — but nothing executes them. Every report flow (rows 6–11)
plugs a `FlowDefinition` into this engine; without the executor they cannot run,
and if each flow re-implemented step progression / date-window / byte-retry /
delivery / error-mapping they would diverge and collide.

This change builds the single, flow-agnostic runtime that all six flows share,
plus the discovery-registry that lets each flow self-register **without any
shared-file edit** (`decomposition-map.md` line 47: `app/flows/__init__.py` is
owned here and uses discovery, not per-flow edits). Guardrails stay per-module
and externalized (§2.2) — the engine reads each flow's frozen config, it does
not hardcode floors, caps, or copy.

## What Changes

Everything here is the **deterministic executor + registry**. No LLM calls (the
router owns those), no HTTP transport (the adapters own that), no rendering (the
widget owns that), no new contracts (imported frozen from change 0).

- **State-machine executor** over the frozen `FlowState`/`Step` types: given the
  current `FlowState`, a `FlowDefinition` (from the flow module), and a user
  event (chip tap / calendar selection / free-text-extracted param / resend),
  compute the next `FlowState` and the ordered render blocks (stepper card,
  calendar, file card, error bubble …) to emit. Pure, deterministic, testable.
- **Step progression** — resolve the next incomplete step from the flow's ordered
  steps; pre-fill steps already satisfied by router-`ExtractedParams`; emit the
  stepper card with completed steps still tappable.
- **Stepper-edit semantics** (`02` §8.4) — reopening a completed step **clears
  all downstream selections**; the prior file card stays in chat history;
  **nothing is re-fetched until the generation step**; cache is keyed per
  selection so edits cause no cross-contamination.
- **≤2 follow-up enforcement hook** — a per-ambiguity counter the engine enforces;
  after two unresolved follow-ups it stops asking and emits the escalation
  affordance (raise-ticket / call-support chips). The router decides *whether* a
  turn is a follow-up; the engine enforces the **cap** and the escalation
  transition.
- **Per-flow date-window enforcement** (`02` §2.5, §8.3) — from each flow's frozen
  window config (floors: Ledger `2019-01-01`, Contract Note / Global Detail / P&L
  `2018-01-01`; caps: `today+7` vs `today`; P&L 2-year max-range clamp, Ledger /
  Global Detail none): emit a calendar render block with **hard-disabled**
  out-of-range dates (never validate-after), and defensively reject an
  out-of-range selection with the flow's nudge copy. **Windows are not unified** —
  each comes from that flow's config.
- **FY helper use** — the FY-driven flows (Tax) consume the frozen FY helpers
  **implemented in `app/contracts/flow.py`** (`currentFY`, `supportedFYs` = rolling
  current + last 2, `defaultFY = currentFY-1` pre-highlighted, `FY 2025-26 ↔
  "2025-2026"` mapping) plus the AY→FY confirmation step. The engine **imports
  them, never reimplements them** — no FY date math lives in `app/engine/`;
  **the three years are never hardcoded** (Apr-1 rollover). An out-of-window FY
  maps to `E-YEAR` with the 3-FY recovery chips **before any API call**.
- **Byte-validation + one silent retry then E-FETCH** — at the generation step the
  engine invokes the flow's adapter binding to produce a report URL (or raw
  bytes), calls the adapter byte-fetch/validation primitive, and on a
  `FinXFetchError` **retries once silently** (fresh generation → fresh URL →
  refetch); a second failure emits the `E-FETCH` bubble (verbatim second-line
  copy + recovery chips). The engine does **not** re-implement HTTP fetching or
  magic-byte checks — it imports that primitive from `app/finx/adapters/` and
  owns only the retry/error policy around it (see conflict note below).
- **Per-flow 15-min session-scoped selection/byte cache** (`02` §2.5) — cache
  keyed per `(flow, selection-tuple)`, TTL 15 min, scoped to the session;
  **"send it again" / "resend" always bypass the cache** and re-generate. Serves
  the "widget-killed-mid-generation resume" and edit-without-refetch behaviours.
- **Delivery assembly** — build the file-card wire object (size, `PDF`, `password:
  PAN` where the flow declares it, `"Trouble opening it? Tell me."` helper) with a
  **renamed display filename** (server names leak ClientId) — **exception: CML
  keeps `Client_Master_List.pdf`** (`02` §2.6); or, for the email branch, the
  email-confirmation block with the **masked registered email**
  (`san***.harsha@gmail.com`). Also the partial dual-format email-failure block
  (EC-12).
- **Error-code mapping to the shared taxonomy** — map the adapter's typed
  exceptions and in-band business results to `E-NODATA` / `E-YEAR` / `E-TIMEOUT` /
  `E-FETCH` / `E-UNKNOWN`, emitting the **verbatim** bubble copy + recovery-chip
  sets from the frozen `error-taxonomy` config (`02` §8.4). `Reason`/HTTP
  codes/URLs never appear in user copy (`Reason` already stays server-side in the
  adapters). Flow modules must **not** redefine error copy — they emit codes.
- **Flow discovery-registry** (`app/flows/__init__.py`) — imports/scans the flow
  package (importlib/pkgutil) and registers each module's exported `FlowDefinition`
  by `Intent`; the engine looks up the definition by the router's `Intent`.
  **Discovery-based so adding a flow needs no edit to this file** — each flow owns
  only its own `app/flows/<name>.py`.

Tests are fixture-based against fake adapters and the frozen contract fixtures;
**no live API calls, no LLM calls**.

## Capabilities

### New Capabilities

- `flow-engine-runtime`: the deterministic state-machine executor over the frozen
  flow-engine-contract — step progression, stepper-edit semantics, ≤2-follow-up
  and date-window/FY guardrail enforcement, byte-validation + silent-retry +
  E-FETCH, the 15-min selection/byte cache, delivery/file-card/email assembly,
  error-taxonomy mapping, and the discovery-based flow registry.

### Modified Capabilities

None — realizes the `flow-engine-contract` capability's semantics without editing
its frozen types.

## Impact

- **New code**: `app/engine/**` (executor, step progression, guardrail enforcement,
  cache, delivery assembly, error mapping), `app/flows/__init__.py` (registry
  only), `tests/engine/**`.
- **APIs**: no HTTP surface; exposes an in-process engine entry point
  (`advance(...)`) consumed by `conversation-orchestrator` (row 5, depends on 2).
- **Downstream**: unblocks all six flow modules (rows 6–11), which supply
  `FlowDefinition`s the engine executes, and the orchestrator, which drives it.
- **Out of scope**: routing/intent classification (`llm-router`), HTTP transport
  (`finx-http-adapters`), render-block **rendering** (`widget-shell`), and the
  Holding / Global-Detail flows (BLOCKED — no `FlowDefinition` shipped for them).

## Files touched

- `app/engine/**` — the entire executor package.
- `app/flows/__init__.py` — the discovery registry **only** (each
  `app/flows/<name>.py` is owned by its own flow change 6–11; this file never
  needs per-flow edits by design).
- `tests/engine/**` — fixture/fake-adapter tests.

Untouched (imported read-only): `app/contracts/**`, `app/finx/interfaces.py`,
`app/finx/envelopes.py`, `app/finx/models.py`, `app/config/**`, `app/llm/client.py`,
and `app/finx/adapters/**` (the byte-fetch primitive is imported, not edited).
**Lockfiles, migrations, and root config are not touched.**

## Contracts & API structure

Executes the frozen flow-engine-contract types from `app/contracts/**`; emits the
frozen render-block wire types from the `chat-wire-api` contract; reads intents
from the frozen `Intent` enum. Signatures below are indicative and bind to the
frozen contract types.

- `advance(state: FlowState, event: FlowEvent, flow: FlowDefinition, *, ctx: SessionContext) -> FlowStepResult`
  — the core executor step. `FlowEvent` = chip tap / calendar pick / extracted
  param / `resend`. Returns the next `FlowState` + the ordered render blocks.
  Deterministic; no I/O except invoking the flow's adapter binding at the
  generation step.
- `next_step(state, flow) -> Step | None` — step progression; `None` ⇒ ready to
  generate.
- `reopen_step(state, step_id) -> FlowState` — stepper-edit; clears downstream
  selections, preserves history, keys cache per selection.
- `enforce_followups(state) -> Escalation | None` — the ≤2-follow-up cap →
  escalation transition (ticket/call chips) on the third.
- `build_calendar(flow, today) -> CalendarBlock` — hard-disabled out-of-range dates
  from the flow's frozen floor/cap/max-range; `validate_range(flow, from, to)` for
  the defensive reject + nudge.
- `resolve_fy(params, today) -> FinYear | EYearError` — via the frozen FY helpers
  imported from `app.contracts.flow`; out-of-window ⇒ `E-YEAR` (no API call).
- `deliver(flow, params, ctx) -> RenderBlock` — generation + cache lookup/store +
  byte-validation + one silent retry + E-FETCH; returns a file-card or
  email-confirmation block. Consumes `finx.adapters.fetch_report_bytes` and the
  flow's adapter binding.
- `map_error(exc_or_result, flow) -> ErrorBubbleBlock` — typed adapter exceptions /
  in-band results → `E-*` code → verbatim bubble + recovery chips from the frozen
  `error-taxonomy`.
- `register(flow_def) -> None` / discovery in `app/flows/__init__.py` — `Intent →
  FlowDefinition` lookup, populated by importlib scan of the flow package.

**Error behaviour**: business no-data ⇒ `E-NODATA`; out-of-window FY ⇒ `E-YEAR`;
`FinXTimeoutError` ⇒ `E-TIMEOUT`; `FinXFetchError` after one silent retry ⇒
`E-FETCH`; any other non-success ⇒ `E-UNKNOWN`. Selections are preserved on
`E-TIMEOUT`/`E-FETCH` (copy promises "your selections are saved").

## Dependencies & contracts consumed

**Consumes (frozen, imported read-only) from `contracts-foundation` (change 0):**
- `app/contracts/**` — `FlowState`, `Step`, transition types, per-flow date-window
  config schema, the FY helpers implemented in `app/contracts/flow.py`
  (`currentFY`/`supportedFYs`/`defaultFY`/short↔long mapping — imported, not
  reimplemented), byte-validation + 15-min-cache typed config, the `chat-wire-api` render-block
  types (stepper/calendar/file-card/error-bubble/ticket-confirmation),
  `error-taxonomy` copy+chips, and the `Intent` enum.
- `app/finx/interfaces.py`, `app/finx/models.py` — types the flow adapter bindings
  return.

**Consumes from `finx-http-adapters` (change 1):**
- `app/finx/adapters/…fetch_report_bytes` and the typed `FinXTimeoutError` /
  `FinXFetchError` / `FinXAuthError` exceptions (imported, not edited).

**Must land first:** change 0 (hard gate). Change 1 must land before the engine's
delivery path can run end-to-end, **but** the engine can be built in parallel
against a fake byte-fetch/adapter (the interface is frozen in change 0) and wired
to the real primitive once change 1 lands — consistent with the ownership map
(engine depends on 0; flows depend on 0,1,2).
**Parallel-safe with:** the six flow modules (they own disjoint `app/flows/<name>.py`;
this change owns only `app/flows/__init__.py`, which never needs their edits).

## Done condition & test command

Done when: `advance()` drives a flow from first step through generation and
delivery deterministically; stepper-edit clears downstream and refetches nothing
until generation; the ≤2-follow-up cap escalates on the third; calendars
hard-disable out-of-range dates and out-of-window FYs yield `E-YEAR` with no
adapter call; a `FinXFetchError` triggers exactly one silent retry then `E-FETCH`;
the 15-min cache returns the cached bytes within TTL and `resend` bypasses it;
delivery renames display filenames (CML excepted) and masks the email; error
mapping emits the verbatim §8.4 copy; and the registry discovers a test
`FlowDefinition` with no edit to `app/flows/__init__.py`.

Test command: `pytest tests/engine/` — green (fake adapters + frozen contract
fixtures; zero network, zero LLM).
