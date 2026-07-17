# Proposal: widget-shell

## Why

The Choice Jini chat widget is the only user-facing surface in Phase 1, yet no
frontend code exists — `docs/prototype/` holds static HTML mockups, not a
runnable React app. Per `CLAUDE.md`, shared contracts land in main before
fan-out; the `chat-wire-api` capability in `contracts-foundation` freezes the
render-block wire types and the session-bootstrap params, so the widget can be
built in full parallel with the backend by rendering fixtures against a mock
server. This change delivers that React app: it consumes the frozen wire
contract and reproduces the locked visual system in `docs/prototype/DESIGN_BRIEF.md`
and the annotated screens in `docs/prototype/screens/`.

The widget owns `widget/**` exclusively, including its own `package.json` and
lockfile — the only frontend dependency graph in the repo. It touches no backend
file. Its sole network surfaces are `POST /api/chat` (the wire contract) and a
static remote-config fetch; every FinX/Freshdesk call, byte fetch, and report
URL stays server-side and never reaches this code (spec §2.3 step 6, §2.6).

## What Changes

A React single-page widget (Vite + TypeScript) that:

- **Renders every render-block wire type** from the frozen `chat-wire-api`
  contract as a typed, discriminated-union component set: `bubble` (bot/user),
  `chip-row`, `stepper-card`, `calendar`, `file-card`, `note-list`, `data-card`,
  `error-bubble`, `ticket-confirmation`. The response is an ordered array of
  these blocks; the widget appends them to the message list in order and never
  reorders or synthesizes blocks the server did not send.
- **Editable stepper card** — completed steps show the chosen value and stay
  tappable; reopening a step clears all downstream selections (spec §8.4
  "Stepper edit semantics"); the prior file card stays in chat history; nothing
  is re-fetched client-side — reopening emits a new `POST /api/chat` turn whose
  body carries the edited selection, and the server owns cache/refetch.
- **In-chat calendar** — month grid with out-of-range dates **hard-disabled**
  (greyed, `line-through`, not clickable), not post-validated. Per-flow bounds
  (`floor`, `cap`, `maxRangeDays`) arrive in the `calendar` block payload from
  the server; the widget obeys them and never computes or hardcodes windows
  (spec §2.5 — windows differ per flow by design).
- **File card** — name, size, `PDF`/`XLS` type, conditional password hint
  ("password: PAN") and a "Trouble opening it? Tell me." helper that emits a
  clarification turn. Download/email actions are server-driven action tokens;
  the widget never holds a report URL or `file_id`.
- **Paginated note-list card** — 10 rows/page, month dividers, per-row Download,
  conditional segment badge (NSE·BSE vs MCX) rendered only when the block marks
  a day as dual-note, "email-all" footer action. Pagination is client-side over
  the block's row array; rows keyed by the block-supplied opaque row id.
- **Data card** — brokerage/holdings rows rendered **dynamically** from the
  block's `groups[]`/`rows[]`; `desc` text rendered verbatim; no computed rupee
  figures, no hardcoded segments or row counts (spec §8.4 "Brokerage render
  contract").
- **Error bubble** — conversational, `--warn`/`--danger` accent, recovery chips;
  never a toast. Code, copy, and chip set come verbatim from the server block
  (error taxonomy owned by `error-taxonomy`); the widget renders, it does not
  author error copy.
- **Ticket confirmation** — ticket id + "within 24 hours" + "ask 'ticket
  status'" line + call-support chip.
- **Two entry surfaces**, both server-seeded via the first `POST /api/chat`
  response using the URL `page` param: **1a Support section** (time-aware
  greeting + "Popular right now" chips + free text) and **1b Reports screen**
  (fulfilment-only chips + rotating input placeholder). The widget selects which
  seed to request from `page`; greeting text, chip sets, and placeholder pool
  are server/remote-config supplied, never hardcoded.
- **Shell & platform behavior** — WhatsApp-style frame ~400×640 floating
  bottom-right on web (collapse to bubble, unread badge, position persists via
  `localStorage`); full-screen slide-up (280ms) in the app WebView with
  swipe-down dismiss. Header (avatar ✦, "● online · <ClientId>", "↺ Start
  over"), scrollable message list, chip-row/composer, and a **persistent
  compliance footer** ("Factual answers only — never investment advice." +
  "Files land right here — no email verification.").
- **Bootstrap** from URL query params (`userId`, `sessionId`, `accessToken`,
  `isDarkTheme`, `platform`, `page`) — parsed once at mount, held in memory,
  echoed on each `POST /api/chat` (§2.3 step 1). `accessToken` is never logged
  or persisted.
- **Theming** — light/dark from FinX tokens (DESIGN_BRIEF §"Design tokens"),
  driven by `isDarkTheme` param with `prefers-color-scheme` fallback; **system
  font stack only — never load a web font** (spec §8.1 decision).
- **Non-streaming request/response cycle** — one JSON response per turn; a
  "Generating…" indicator appears when a turn exceeds 5s (§8.2). Message cap (10)
  and follow-up cap (2) are enforced server-side and surfaced by the blocks the
  server returns; the widget does not re-implement the caps.

- **WebMCP page-tool registration (agent-native surface, additive)** — the
  widget registers a small set of page-level tools via the W3C WebMCP draft API
  (`document.modelContext.registerTool({name, description, inputSchema,
  execute})`): `send_message` (free text), `tap_chip` (by actionToken),
  `get_conversation_state` (read-only block log + turn state). Typed against
  the `webmcp-types` npm package (dev dependency, type definitions only);
  wrapped in feature detection (`if (document.modelContext) …`) so it is a
  silent no-op in every browser that does not implement the draft — no
  polyfill, no runtime dependency, no behavioral change for normal users.
  Registration code lives in `widget/src/webmcp.ts` (widget-owned; no backend
  or contract change — the tools call the same internal actions the UI uses).

**Development strategy:** build against a mock server (or Vite dev middleware /
MSW) that implements the wire contract and serves fixtures for every block type
and both entry seeds, so the widget parallelizes fully with the backend. The
prototype screens in `docs/prototype/screens/` are the visual acceptance
reference. **Agent-driven E2E is part of done** (Gate-1 amendment,
2026-07-17): Claude Code must be able to drive the running widget against the
mock server via the project-scoped Playwright MCP server (`.mcp.json` →
`@playwright/mcp`) or the /browse harness — open the widget, send a free-text
message, walk a stepper via chips, and observe the resulting blocks.

## Capabilities

### New Capabilities

- `widget-shell`: the React chat widget — the shell frame (web floating window +
  app WebView full-screen), URL-param bootstrap, theming, both entry surfaces,
  the full render-block component set for every `chat-wire-api` wire type, and
  the non-streaming turn loop against `POST /api/chat`.

### Modified Capabilities

None — this change consumes `chat-wire-api`, `remote-config`, and `error-taxonomy`
read-only and adds no backend behavior. It does not modify any frozen contract.

## Impact

- **New code**: `widget/` — a self-contained Vite + React + TypeScript app with
  its own `package.json` and lockfile, component library, mock server/fixtures,
  and vitest suite. No backend file, no `pyproject.toml`, no Python.
- **APIs consumed**: `POST /api/chat` (request/response per `chat-wire-api`) and
  a static remote-config GET (chip sets, greeting pool, placeholder pool, limits
  — schema owned by `remote-config`). No other network surface exists in this
  code.
- **Out of scope**: WebMCP beyond registration (no polyfill; native browser
  support does not exist yet — the tools activate automatically when a browser
  agent implements the draft); real backend
  integration (arrives when `conversation-orchestrator` lands `POST /api/chat`);
  holding-file delivery and Global-Detail download (owner-BLOCKED — the widget
  renders holdings only as a `data-card`, never a file card); streaming
  (Phase-1 decision is non-streaming).

## Files touched

Exclusive owner of `widget/**` (per the ownership map, row 15). Nothing outside
it. Backend `pyproject.toml`, lockfile, migrations, and root config are
**untouched** — the widget's `package.json` + lockfile are the only frontend
dependency files and live entirely under `widget/`.

```
widget/
  package.json                 # own dep graph — ONLY frontend lockfile in repo
  package-lock.json            # (or pnpm-lock.yaml) — committed, widget-scoped
  tsconfig.json
  vite.config.ts
  index.html                   # widget host page
  src/
    main.tsx                   # mount, URL-param bootstrap
    bootstrap.ts               # parse userId/sessionId/accessToken/isDarkTheme/platform/page
    webmcp.ts                  # WebMCP page-tool registration (webmcp-types devDep; feature-detected no-op)
    theme/
      tokens.css               # FinX design tokens (light + dark), system font stack
      useTheme.ts              # isDarkTheme param + prefers-color-scheme fallback
    shell/
      WidgetFrame.tsx          # web floating ~400x640 (collapse/bubble/unread/position-persist)
      AppSheet.tsx             # WebView full-screen slide-up 280ms + swipe-down dismiss
      Header.tsx               # avatar / online · ClientId / Start over
      Composer.tsx             # input + placeholder + send
      ComplianceFooter.tsx     # persistent disclaimer + trust line
      GeneratingIndicator.tsx  # >5s "Generating…"
    entry/
      SupportEntry.tsx         # 1a greeting + Popular-now chips + free text
      ReportsEntry.tsx         # 1b fulfilment chips + rotating placeholder
    blocks/                    # one component per wire render-block type
      BubbleBlock.tsx
      ChipRowBlock.tsx
      StepperCardBlock.tsx
      CalendarBlock.tsx
      FileCardBlock.tsx
      NoteListBlock.tsx
      DataCardBlock.tsx
      ErrorBubbleBlock.tsx
      TicketConfirmationBlock.tsx
      RenderBlock.tsx          # discriminated-union switch on block.type
    api/
      wireTypes.ts             # TS mirror of chat-wire-api block union (source: contract)
      chatClient.ts            # POST /api/chat, remote-config GET
    state/
      conversation.ts          # append-only block log, turn dispatch
  mock/
    server.ts                  # dev mock implementing the wire contract
    fixtures/                  # one fixture per block type + both entry seeds
  test/
    *.test.tsx                 # vitest + react-testing-library
```

`wireTypes.ts` is a hand-mirrored TypeScript copy of the frozen `chat-wire-api`
block union (the contract is authored in Pydantic under `app/contracts/`, which
this change does not import); it is kept in sync with, and subordinate to, the
Python contract. [CONFIRM] whether `contracts-foundation` will emit a generated
TS/JSON-schema artifact the widget should consume instead of a hand mirror — if
so, the widget imports that and `wireTypes.ts` becomes a thin re-export.

## Contracts & API structure

**Network surface (the only two calls this code makes):**

- `POST /api/chat` — request/response per the `chat-wire-api` contract.
  - Request body (widget → backend): session context echoed from the URL params
    (`userId`, `sessionId`, `accessToken`, `platform`, `page`) plus the turn
    payload — free-text message, or a structured action (chip tap, stepper
    selection/edit, calendar date pick, pagination request, file/note download
    or email action token, recovery-chip tap). Exact field names owned by
    `chat-wire-api`; the widget conforms, does not define.
  - Response body (backend → widget): the non-streaming turn result — an ordered
    array of typed render blocks. The widget appends in order.
  - Error behavior: transport/HTTP failures surface as a client-synthesized
    `E-TIMEOUT`-style error bubble using copy the server/remote-config supplies;
    all in-band domain errors arrive as `error-bubble` blocks (HTTP 200 body).
    The widget never parses raw HTTP codes or `Reason` into user copy (§2.6).
- `GET <remote-config>` — static config fetch (chip sets per entry surface,
  greeting pool, placeholder pool, limits). Schema owned by `remote-config`.
  [CONFIRM] exact path/host with `contracts-foundation` (whether config is
  fetched directly by the widget or folded into the first `/api/chat` response —
  the widget can support either; folding it into the seed response is preferred
  so the widget keeps a single network surface).

**Render-block component contract** — each block type maps to one component;
`RenderBlock.tsx` switches on `block.type` (discriminated union). Prop shapes
are the wire payloads defined by `chat-wire-api`; names below are the block
`type` discriminators from the pinned Phase-1 decision (decomposition map §pinned):

| Wire `type` | Component | Key props (from wire payload) |
|---|---|---|
| `bubble` | `BubbleBlock` | `role` (bot/user), `text`/rich runs, optional `caption` |
| `chip-row` | `ChipRowBlock` | `chips[]` (`{label, actionToken, variant?}`), `wrap` |
| `stepper-card` | `StepperCardBlock` | `title`, `steps[]` (`{id, label, state: active/done/pending, value?, chips?, editable}`) — tapping a `done` step emits an edit action for `step.id` |
| `calendar` | `CalendarBlock` | `mode` (single/range), `floor`, `cap`, `maxRangeDays?`, `month`, `selected?` — out-of-range days hard-disabled |
| `file-card` | `FileCardBlock` | `name`, `sizeLabel`, `kind` (pdf/xls), `passwordHint?`, `actions[]` (download/email tokens), `helperLink` ("Trouble opening it?") |
| `note-list` | `NoteListBlock` | `rows[]` (`{rowId, dayLabel, monthKey, segmentBadge?, downloadToken}`), `pageSize` (10), `footerActions[]` (email-all) |
| `data-card` | `DataCardBlock` | `title`, `groups[]` (`{title, rows:[{k, v}] }`) or `rows[]` — rendered verbatim, dynamic |
| `error-bubble` | `ErrorBubbleBlock` | `code` (E-NODATA/E-YEAR/E-TIMEOUT/E-FETCH/E-UNKNOWN), `severity` (warn/danger), `copy`, `recoveryChips[]` |
| `ticket-confirmation` | `TicketConfirmationBlock` | `ticketId`, `slaText`, `statusHint`, `callChip` |

**Bootstrap contract** — `bootstrap.ts` reads the six URL query params (§2.3
step 1): `userId`, `sessionId`, `accessToken` (JWT), `isDarkTheme`, `platform`
(web/webview), `page` (selects entry seed 1a vs 1b). Held in memory only;
`accessToken` never persisted or logged.

**Shell contract** — `WidgetFrame` (web): floating ~400×640, collapse→bubble,
unread badge, position persisted in `localStorage`. `AppSheet` (webview):
full-screen, 280ms slide-up, swipe-down dismiss. Chosen by `platform` param.

No FinX or Freshdesk endpoint is referenced anywhere in this change; report
URLs, `file_id`s, and raw API errors never reach this code (spec §2.6).

## Dependencies & contracts consumed

**Consumes (read-only, from `contracts-foundation`):**

- `chat-wire-api` — the render-block wire union, the `POST /api/chat`
  request/response schema, and the session-bootstrap param set. This is the only
  hard dependency; the widget cannot render blocks until the block `type`
  discriminators and payload shapes are frozen.
- `remote-config` — chip sets per entry surface, greeting pool, placeholder
  pool, limits (page size 10). Consumed for fixture shapes and runtime config.
- `error-taxonomy` — error codes, verbatim copy, recovery-chip sets. Consumed
  only to shape the `error-bubble` fixtures; the server authors the copy at
  runtime.

**Must land first:** `contracts-foundation` (change 0) — specifically the frozen
`chat-wire-api` block shapes. Until then the widget builds against a local
mirror in `wireTypes.ts` seeded from the contract draft.

**Runs fully in parallel with:** every backend change (1–14) and `eval-harness`
(16). The widget shares **no file** with any of them and reaches the backend
only through `POST /api/chat`, which `conversation-orchestrator` (change 5)
implements — but the widget does not need it to build or test, because the mock
server implements the same wire contract. Integration against the real endpoint
happens after both land; no merge conflict is possible (disjoint directories).

**No conflicts with other proposals:** a repo-wide scan of
`openspec/changes/*/proposal.md` shows no other change references `widget/` or
any frontend `package.json`/lockfile. `widget-shell` is the sole owner of the
frontend dependency graph per the ownership map.

## Done condition & test command

**Done when:**

1. Every render-block wire type (`bubble`, `chip-row`, `stepper-card`,
   `calendar`, `file-card`, `note-list`, `data-card`, `error-bubble`,
   `ticket-confirmation`) renders from a fixture and matches its counterpart
   screen in `docs/prototype/screens/` (pnl, ledger, contract-notes, tax, cml,
   brokerage, holding, rag, ticketing).
2. Both entry surfaces render from their seed fixtures — 1a Support (greeting +
   Popular-now chips + free text) and 1b Reports (fulfilment chips + rotating
   placeholder) — selected by the `page` URL param.
3. Interaction contracts verified by test: stepper edit clears downstream
   selections; calendar hard-disables out-of-range dates (per block-supplied
   `floor`/`cap`/`maxRangeDays`); note-list paginates 10/page with month
   dividers and conditional segment badge; data-card renders arbitrary dynamic
   `groups[]` without hardcoding.
4. Shell behaviors verified: web frame collapses to a bubble with unread badge
   and persists position; app WebView renders full-screen; theming follows
   `isDarkTheme` with `prefers-color-scheme` fallback and loads no web font;
   compliance footer always present; "Generating…" indicator appears past 5s.
5. The turn loop issues exactly one `POST /api/chat` per user action against the
   mock server and appends returned blocks in order; `accessToken` never appears
   in logs or persisted storage.

6. WebMCP registration verified by unit test: with a mocked
   `document.modelContext`, the three page tools register with valid
   input_schemas and `execute` routes to the same internal actions the UI
   uses; with `document.modelContext` absent, the widget boots identically
   (feature-detected no-op).
7. **Agent-driven E2E (required)**: an agent session (project-scoped
   Playwright MCP from `.mcp.json`, or /browse) drives the built widget
   against the mock server — loads the entry surface, sends a free-text
   message, taps chips through a stepper to a file card, and asserts the
   rendered blocks. This proves "Claude Code can test the frontend" as a
   deliverable, not an afterthought.

**Test command:** `npm --prefix widget test` (vitest + react-testing-library,
fixture-based, no live API). Type safety: `npm --prefix widget run typecheck`
(tsc `--noEmit`). E2E: the agent-driven pass above, run against
`npm --prefix widget run dev:mock`.
