# Proposal: flow-brokerage

## Why

"What are my brokerage charges?" is the validated explanation-intent chip on the Entry-1 support screen (spec §8, flow spec "Main Page"). Unlike the report flows, brokerage is **not a stepper flow** — per the flow spec ("Brokerage: This is not flow. We need to call this API on the intent click or Free Text"), it is a single API call on intent that renders a dynamic data card of the client's rate slabs. This change is the self-contained Brokerage flow module, registering with the engine's discovery registry.

The endpoint is `get-brokerage-slab` (03 §4.6c, live-captured 2026-07-16). Its `Response` is an **array of segment groups** `{title, list:[{title, desc}]}` where `desc` is **pre-formatted human-readable rate text** ("₹0.10 for trade value of 10 thousand"). Two hard product rules: **render `desc` verbatim — never parse or compute a rupee figure** (rates only, point to the contract note; flow spec EC-5), and **render dynamically — slabs differ per client**, so never hardcode the segments or the row count (03 §4.6c owner note).

## What Changes

- New flow module `app/flows/brokerage.py` implementing a single-shot (no-step) intent handler against the frozen `FlowState`/`Step` and `FinXClient` contracts; self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry auto-loads by module presence — **no edit to `app/flows/__init__.py`**.
- On intent (chip or free text): one `POST get-brokerage-slab` call → render the returned `Response` array as a **data card**, iterating whatever groups/rows the API returns.
- Each group renders `{title, list:[{title, desc}]}` with `desc` **verbatim**; no computed figures, no PDF, no email (there is no document for brokerage — EC-7).
- Edge cases from the flow spec: EC-1 API failure/timeout → one silent retry then "Couldn't fetch your brokerage details just now." + retry/ticket chips; EC-4 segment-not-in-plan → show the plan + ticket chip for the rest; EC-5/EC-6 calculation asks → show the rate row + contract-note pointer, never compute; EC-8/EC-10 session-scoped cache only (fresh session = fresh fetch).

## Capabilities

### New Capabilities

- `flow-brokerage`: the single-shot Brokerage data-card flow — `get-brokerage-slab` call on intent, dynamic rendering of the per-client segment/slab groups with `desc` verbatim (never computing rupee figures), no PDF/email path, and conversational retry/ticket error handling.

### Modified Capabilities

None — new self-contained flow capability; frozen contracts untouched.

## Impact

- **New code**: `app/flows/brokerage.py` + `tests/flows/test_brokerage.py`. No new dependencies.
- **APIs**: consumes `get-brokerage-slab` server-side only (SSO JWT auth).
- **No file delivery**: brokerage is card-only by design — no byte validation, no file card, no email/PDF path (EC-7). Session-scoped render cache only.
- **Lockfiles / migrations / root config**: untouched.

## Files touched

Exactly two files (the complete ownership for this change):

- `app/flows/brokerage.py` — the Brokerage flow module. Self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry (`app/flows/__init__.py`, owned by flow-engine-runtime) auto-loads by module presence — no registration import is added anywhere.
- `tests/flows/test_brokerage.py` — the fixture-based flow test.

**Not touched**: `app/flows/__init__.py` (discovery registry, owned by flow-engine-runtime), any other `app/flows/*.py`, any shared/contract file, and lockfiles / migrations / root config.

## Contracts & API structure

### FinX endpoint — `POST https://api.choiceindia.com/middleware-go/v2/get-brokerage-slab` (03 §4.6c)

- **Backend**: Go middleware on the `api.choiceindia.com` host (same host as the contract-note download). **Auth**: `authorization: <SSO JWT = frontend accessToken>` (JWT, **not** the SessionId). **Envelope**: hybrid — carries **both** `StatusCode` and `Status` (a blend of the two conventions). Consumed via the `api.` JWT adapter (finx-http-adapters, 1) behind `FinXClient`.

Request contract (exactly as captured):

```json
{ "ClientID": "<client code>" }
```

- **Identity-field trap**: request key is **`ClientID`** — PascalCase, one word (distinct from `ClientId`, `client_id`, `client_code`, `searchValue` used elsewhere). Bound to the authenticated session.

Response contract (live-captured, HTTP 200) — hybrid envelope:

```json
{
  "StatusCode": 200,
  "Status": "Success",
  "Response": [
    { "title": "Equity", "list": [
        { "title": "Intraday", "desc": "₹0.10 for trade value of 10 thousand" },
        { "title": "Delivery", "desc": "₹1.00 for trade value of 10 thousand" } ] },
    { "title": "Derivative", "list": [
        { "title": "Stock Future", "desc": "₹20.00 for trade value of 10 thousand" },
        { "title": "Stock Option", "desc": "₹20.00 per order" } ] }
  ],
  "Reason": ""
}
```

- **`Response` = array of segment groups**, each `{ title: string, list: [{ title: string, desc: string }] }`.
- 🔻 **Render rules (hard)**: iterate whatever `Response` returns — **do NOT hardcode Equity/Derivative/Commodity/Currency or a fixed row count** (segments and rows-per-segment vary per client). Render `desc` **verbatim** — do NOT parse or compute a rupee figure.
- No documented no-data/failure envelope beyond the hybrid success; treat a missing/empty `Response` array or non-Success `Status`/`StatusCode` as a fetch failure.

Error mapping (flow spec, not the report E-* file taxonomy): API failure / timeout → **one silent retry**, then "Couldn't fetch your brokerage details just now." + [↺ Retry · 🎫 Raise a ticket]; never a toast. `Status`/`Reason` logged server-side only.

### Flow step / render-block sequence

1. `[INTENT: brokerage]` (chip or free text) → single `get-brokerage-slab` call (no user-input step); "…" ack `bubble`.
2. Render: `data-card` built dynamically from `Response` — one section per group `title`, each row `{title, desc}` with `desc` verbatim.
3. Calculation / off-plan asks → `bubble` (rate row + contract-note pointer) + `chip-row` [Show my ledger · 🎫 Raise a ticket]; "email/PDF me my brokerage" → `bubble` "there's no document for this one" + the card.
4. Failure: `error-bubble` + `chip-row` [↺ Retry · 🎫 Raise a ticket] (after one silent retry).

## Dependencies & contracts consumed

- **Imports (frozen, read-only)**: `FlowState`/`Step` + session-scoped cache semantics (`flow-engine-contract`); `Intent.BROKERAGE` (`router-contract`); `FinXClient` + `get-brokerage-slab` models + the hybrid-envelope parser (`finx-client`); `chat-wire-api` `data-card` render-block type; `error-taxonomy` (retry/ticket chips). Requires the widget to forward `accessToken` (SSO JWT) per the `chat-wire-api` session-bootstrap contract.
- **Must land first**: contracts-foundation (0). **Consumes at runtime**: the `api.` JWT adapter (1) + engine executor/discovery registry (2). Builds against contracts + fakes; parallel-safe with 1, 2 once 0 lands.
- **Parallel-safe with the other five flow changes**: no shared file edited; registration via discovery. **Shares the JWT-auth adapter with flow-cml** — a contract dependency on finx-http-adapters, not a file conflict. **Coordination note**: relies on the widget shell (change 15) implementing the `data-card` render-block per the frozen `chat-wire-api` wire type, and on the same dynamic `data-card` used by the spec §8.4 brokerage render contract.

## Done condition & test command

Done when: `app/flows/brokerage.py` is discovered/registered; the intent (chip or free text) drives one `get-brokerage-slab` call with `{ClientID:<session client>}` over the JWT adapter; the `Response` array renders as a data card with segments and rows **iterated dynamically** and `desc` **verbatim** (a fixture with a non-standard segment set / row count proves no hardcoding, and no rupee figure is ever computed); no PDF/email path exists; API failure triggers one silent retry then the conversational error bubble. Against **fixture-based FinX mocks** (a multi-segment slab fixture + a variant fixture with different segments/rows + a failure fixture) — no live API.

Test command: `pytest tests/flows/test_brokerage.py`
