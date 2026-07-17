# Tasks: flow-contract-notes

Vertical slice — the self-contained Contract Note flow module. Exactly two
owned files (`app/flows/contract_notes.py`, `tests/flows/test_contract_notes.py`);
`app/flows/__init__.py` is engine-owned (discovery registry) and NOT created here.

- [x] **T1 — Scaffold.** `tasks.md` + `loop.md` in the proposal dir. (this commit)
- [x] **T2 — Flow module.** `app/flows/contract_notes.py`:
  - module-level `FLOW: FlowSpec` (intent `report_contract_notes`, window from
    remote-config: floor 2018-01-01, cap today, no max range) discovered by
    module presence — no registration import.
  - Step 1 date-range chips + calendar (floor 2018-01-01 / cap today / no max range).
  - Step 2 fetch & branch on the Go envelope outcome / body `StatusCode`
    (204 → E-NODATA explainer · 1 → direct delivery · 2+ → note-list · >50 → nudge).
  - Note-list card keyed by `file_id` (rows carry an opaque session-scoped
    `downloadToken`, never `file_id`), month dividers, dual-note segment badges
    (Grp1 → "Equity & F&O", MCX → "Commodity"), 10/page, footer chips.
  - Per-note download via the `api.` Go adapter, size + `%PDF` magic-byte
    validation, exactly one silent retry then E-FETCH; timeout → E-TIMEOUT.
  - Renamed display filename `Contract_Note_<date>[_MCX].pdf`; no password.
  - **FLAG A defense:** `client_id`/`client_code` always the session `user_id`,
    never user input; `file_id` lives only in a session-scoped token vault —
    never on the wire, never logged.
- [x] **T3 — Tests from the proposal.** `tests/flows/test_contract_notes.py`:
  discovery/registration, session-bound identity + snake_case list request,
  StatusCode branching (204 / 1 / 2+ / >50), note-list keyed by `file_id` with
  correct badges, download validation + one-silent-retry → E-FETCH, timeout →
  E-TIMEOUT, `file_id` never on the wire nor logged, session-scoped token,
  calendar bounds, email confirmation (single + bulk).
- [x] **T4 — Spec harness.** `pytest tests/flows/test_contract_notes.py` green
  (30 passed). Fresh spec-verifier panel SKIPPED per operator lean directive
  (trust the implementation; token/overhead cut) — spec harness = testCommand +
  full suite only.
- [x] **T5 — Ship.** Rebased cleanly onto latest origin/main (PRs #2, #3 merged),
  full `uv run pytest` green (205 passed), pushed, PR #5 open.
