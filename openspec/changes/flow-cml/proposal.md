# Proposal: flow-cml

## Why

The Client Master List (CML) is a frequent request (typed from the Entry-2 long-tail hint line; flow spec "CML Flow") and the simplest flow — no user input at all: intent → API → PDF in chat. This change is the self-contained CML flow module, registering with the engine's discovery registry.

CML is served by the **third backend** `POST /mis/reports/generate` (03 §4.3, live-captured 2026-07-16), which authenticates with the **SSO JWT** (`authType: jwt` + `authorization: <accessToken>` + `source: FINX_ANDROID`) — **not** the SessionId. **CML fails if handed the SessionId** (03 §1), so this flow depends on the JWT-auth adapter and the widget forwarding `accessToken`. Two carve-outs apply: CML **keeps the server's own filename `Client_Master_List.pdf`** (the one naming exception — it contains nothing sensitive; spec §2.6), and the signed URL's `X-Amz-Expires=120` / "single-use" is **NOT a security boundary** (03 §7 FLAG B — CloudFront path-only caching defeats it) — so always fetch server-side and never surface or log the link.

## What Changes

- New flow module `app/flows/cml.py` implementing the zero-step CML flow against frozen `FlowState`/`Step` and `FinXClient` contracts; self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry auto-loads by module presence — **no edit to `app/flows/__init__.py`**.
- On intent: single `POST /mis/reports/generate` call → read `body.cmlLink` → backend fetches bytes within seconds → byte-validate (`%PDF`) → deliver as a file card. The link is discarded immediately, never cached, never logged, never sent to the client.
- File card keeps the server filename **`Client_Master_List.pdf`** (naming carve-out), no password line **[CONFIRM — assumed unprotected]**, helper line "Trouble opening it? Tell me."
- Post-delivery chips: ↺ Send it again (re-calls the API — the old link is dead; only byte-cache may be reused, never the link) · Something incorrect in it? 🎫 Raise a ticket (high-frequency CML follow-up is an address/bank/nominee service request, not a re-download).
- "Getting your CML…" progress line if generation >5s.

## Capabilities

### New Capabilities

- `flow-cml`: the zero-step CML report flow — SSO-JWT-authenticated `POST /mis/reports/generate` call, `body.cmlLink` server-side fetch + byte validation, file card keeping the `Client_Master_List.pdf` server filename, always-server-side handling of the non-boundary signed URL (FLAG B), and the E-* error taxonomy.

### Modified Capabilities

None — new self-contained flow capability; frozen contracts untouched.

## Impact

- **New code**: `app/flows/cml.py` + `tests/flows/test_cml.py`. No new dependencies.
- **APIs**: consumes `/mis/reports/generate` server-side only (SSO JWT). `cmlLink` never surfaced or logged; fetched immediately and discarded (FLAG B — expiry/single-use is not relied upon).
- **[CONFIRM] carried forward**: CML PDF password status (`[ASSUMPTION]` — assumed unprotected; spec §9 item 12); `source: FINX_ANDROID` gating unconfirmed (03 §1); the generic report-generator shape (`reportType`/`searchBy`/`searchValue`) has only `cml` confirmed. Static pre-generated S3 object may be **stale** vs the current master list (FLAG B).
- **Lockfiles / migrations / root config**: untouched.

## Files touched

Exactly two files (the complete ownership for this change):

- `app/flows/cml.py` — the CML flow module. Self-registers by exposing a module-level `FLOW` definition that the engine's **importlib discovery** registry (`app/flows/__init__.py`, owned by flow-engine-runtime) auto-loads by module presence — no registration import is added anywhere.
- `tests/flows/test_cml.py` — the fixture-based flow test.

**Not touched**: `app/flows/__init__.py` (discovery registry, owned by flow-engine-runtime), any other `app/flows/*.py`, any shared/contract file, and lockfiles / migrations / root config.

## Contracts & API structure

### FinX endpoint — `POST /mis/reports/generate` (03 §4.3)

- **Backend**: MIS reports (third backend). **Casing**: camelCase. **Envelope**: camelCase `{statusCode, message, devMessage, body}`. **Auth**: `authType: jwt` + `authorization: <SSO JWT = frontend accessToken>` + `source: FINX_ANDROID` (**SessionId will NOT work here**). Consumed via the MIS/JWT adapter (finx-http-adapters, 1) behind `FinXClient`.

Request contract (exactly as captured):

```json
{ "reportType": "cml", "searchBy": "client-id", "searchValue": "<client code>" }
```

- **`searchValue`** = client code, bound to the authenticated session (never user-supplied).
- Shape suggests a **generic report generator**; only `cml` confirmed **[CONFIRM]**.

Response contract (live-captured, HTTP 200) — **camelCase envelope** (differs from the Go PascalCase):

```json
{ "statusCode": 200, "message": "URL generated successfully", "devMessage": null,
  "body": { "cmlLink": "https://onmedia.choiceindia.com/JF/<hash>/<hash>_CML_<ts>.pdf?X-Amz-Algorithm=...&X-Amz-Expires=120&...&response-content-disposition=attachment%3B%20filename%3DClient_Master_List.pdf&X-Amz-Signature=..." } }
```

- Link field: **`body.cmlLink`** — an AWS S3 SigV4 pre-signed URL (`X-Amz-Expires=120`) fronted by CloudFront. Download filename (from content-disposition) `Client_Master_List.pdf` — **keep it** (§2.6 carve-out). PDF verified `%PDF-1.6`.
- 🔴 **FLAG B**: `X-Amz-Expires=120`/single-use is **not enforced** (CloudFront caches by path, ignoring the signed query string). Do NOT rely on expiry as a boundary; fetch server-side immediately, discard the link.
- Auth failure: HTTP **401** `{"statusCode":401,"message":"Invalid Request.","devMessage":null,"body":{}}` (differs from the .NET 401 envelope — detect by status code).

Error mapping: missing/empty `body.cmlLink` or non-200 `statusCode` → `E-UNKNOWN`; fetched bytes 404 / wrong magic → `E-FETCH` (silent retry via a fresh API call — the old link is dead); timeout → `E-TIMEOUT`. `message`/`devMessage` logged server-side only, never shown.

### Flow step / render-block sequence

1. `[INTENT: cml]` → **Step 1 · Generate + deliver** (no user input) — `bubble` ack; "Getting your CML…" if >5s.
2. Deliver: `file-card` (server filename `Client_Master_List.pdf`, size, `PDF`, no password line, helper line).
3. Post-delivery `chip-row` [↺ Send it again · Something incorrect in it? 🎫 Raise a ticket].
4. Failures: `error-bubble` + recovery `chip-row` [↺ Send it again · 🎫 Raise a ticket].

## Dependencies & contracts consumed

- **Imports (frozen, read-only)**: `FlowState`/`Step` + byte-validation/cache semantics (`flow-engine-contract`); `Intent.CML` (`router-contract`); `FinXClient` + `/mis/reports/generate` models + the MIS/JWT camelCase parser (`finx-client`); `error-taxonomy`; `chat-wire-api` render-block types. Requires the widget to forward `accessToken` (SSO JWT) per the `chat-wire-api` session-bootstrap contract.
- **Must land first**: contracts-foundation (0). **Consumes at runtime**: the MIS/JWT adapter (1) + engine executor/byte-cache/discovery registry (2). Builds against contracts + fakes; parallel-safe with 1, 2 once 0 lands.
- **Parallel-safe with the other five flow changes**: no shared file edited; registration via discovery. **Shares the JWT-auth adapter with flow-brokerage** — a contract dependency on finx-http-adapters, not a file conflict.

## Done condition & test command

Done when: `app/flows/cml.py` is discovered/registered; the intent immediately drives `/mis/reports/generate` with `{reportType:"cml", searchBy:"client-id", searchValue:<session client>}` over the **JWT adapter** (SessionId is never used); `body.cmlLink` is fetched server-side, byte-validated, and delivered as `Client_Master_List.pdf` with no password line; the link is never cached/logged/surfaced; "Send it again" re-calls the API rather than reusing the link; auth/fetch/unknown failures map to correct E-* bubbles. Against **fixture-based FinX mocks** (CML success + 401 fixtures + a `%PDF` byte fixture) — no live API.

Test command: `pytest tests/flows/test_cml.py`
