# Tasks: flow-cml

Two owned files; the engine (change 2) and adapters (change 1) are consumed via
frozen contracts + injected fakes. Built and tested standalone (no live API, no
engine, no network).

## T1 — Scaffold + loop state
- [ ] Author `tasks.md` (this file) and `loop.md`.
- [ ] Create empty `tests/flows/__init__.py` (test package marker; `app/flows`
      is a PEP 420 namespace package — no `app/flows/__init__.py`, that file is
      engine-owned/frozen).

## T2 — Implement `app/flows/cml.py`
- [ ] Module-level `FLOW: FlowSpec` (intent `Intent.report_cml`, `FlowConfig`
      with an empty `DateWindow` — CML has no calendar, no user input) so the
      engine's importlib discovery auto-registers it; `steps()` yields the single
      `generate` step.
- [ ] Build the frozen `CmlRequest{reportType:"cml", searchBy:"client-id",
      searchValue:<session client_id>}` and call `client.mis.generate_report`
      (JWT/MIS adapter). SessionId is never read or sent (the frozen `CmlRequest`
      has no SessionId field; the flow reads `ctx.user_id`, never
      `ctx.session_id`).
- [ ] Parse `body.cmlLink` via the frozen `CmlBody`; fetch bytes server-side via
      an injected async fetcher; byte-validate with the frozen `ByteValidation`
      (`min_bytes` + `%PDF` magic). The link is never cached, logged, surfaced, or
      placed in any render block (FLAG B — expiry/single-use is not a boundary).
- [ ] Deliver a frozen `FileCard` keeping the server filename
      `Client_Master_List.pdf` (§2.6 carve-out), `format="pdf"`,
      `password_hint=None` ([ASSUMPTION] unprotected — spec §9 item 12), default
      helper line; plus a post-delivery `ChipRow`
      [↺ Send it again · Something incorrect in it? 🎫 Raise a ticket].
- [ ] "Send it again" always re-calls `generate_report` for a fresh link (the old
      link is dead); one silent byte-validation retry (`silent_retries=1`) is also
      a fresh API call.
- [ ] Map failures to the frozen error taxonomy (emit codes, do NOT redefine
      copy): auth-401 / non-200 / missing cmlLink → `E-UNKNOWN`; wrong magic /
      too-small bytes after one silent retry → `E-FETCH`; timeout → `E-TIMEOUT`.
      Render `ErrorBubble` text + recovery chips from frozen `ERROR_COPY`.
- [ ] Expose the ">5s" latency copy "Getting your CML…" as a declaration for the
      engine's `Generating` block.

## T3 — Write `tests/flows/test_cml.py` (from the proposal, fixture-based)
- [ ] Discovery: `FLOW` satisfies `FlowSpec`, `intent == Intent.report_cml`.
- [ ] Request shape + JWT: `generate_report` receives the exact `CmlRequest`;
      `searchValue == ctx.user_id`; SessionId never used.
- [ ] Success: server-side fetch → `%PDF` validate → `FileCard`
      (`Client_Master_List.pdf`, no password); link absent from every block.
- [ ] Resend re-calls the API (two calls, fresh link each time).
- [ ] One silent retry on wrong magic, then `E-FETCH`.
- [ ] auth-401 → `E-UNKNOWN`; timeout → `E-TIMEOUT`; unknown non-200 →
      `E-UNKNOWN`.

## T4 — Verify + ship
- [ ] `pytest tests/flows/test_cml.py` green (testCommand).
- [ ] One fresh spec-verifier (all three lenses); fix blocking findings.
- [ ] Rebase onto latest origin/main; full `uv run pytest` green; push; open PR.
