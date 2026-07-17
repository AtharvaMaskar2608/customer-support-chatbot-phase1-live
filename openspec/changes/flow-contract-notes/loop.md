# loop.md — flow-contract-notes

Resume-from-this-file log. If it isn't here, it didn't happen.

## Assignment

- Change: **flow-contract-notes** (Wave 1, full fan-out). Owner directive:
  small change, target PR ~30 min.
- Branch/worktree: `flow-contract-notes` @ main `cfb22a1` (contracts-foundation
  merged, Wave 0 landed).
- Owned files (manifest): `app/flows/contract_notes.py`,
  `tests/flows/test_contract_notes.py`. Plus `tests/flows/__init__.py` (empty
  package marker — needed for pytest import; the ONLY extra file).
- doneCondition / testCommand: `pytest tests/flows/test_contract_notes.py`.

## Frozen-surface findings (read-only, verified present & correct)

- Intent is `Intent.report_contract_notes` (proposal's `Intent.CONTRACT_NOTES`
  is shorthand). `app/contracts/router.py`.
- Go envelope + parser: `app/finx/envelopes.py` `parse_go_envelope` branches on
  body `StatusCode` (200 success / 204+empty-body no_data / else error) — this
  is the "branch on body StatusCode, never HTTP" contract, already frozen.
- FinX models `app/finx/models.py`: `ContractNoteListRequest{client_id,
  from_date,to_date}` (snake, no SessionId), `ContractNoteDownloadRequest{
  client_code,file_id}`, `ContractNote{date DDMMYYYY, file_id, group, id,
  invoice_number}` (`by_file_id()` — key by file_id, never id),
  `ContractNoteDownloadResponse = bytes`.
- Client protocol `app/finx/interfaces.py`: `FinXClient.go: GoMiddlewareAdapter`
  → `list_contract_notes(req) -> ParsedEnvelope`, `download_contract_note(req)
  -> bytes`. Header/prefix auth (header-only list; `Session `-prefix download)
  is ADAPTER-owned (finx-http-adapters, change 1) — NOT this flow's surface.
- Wire `app/contracts/wire.py`: `NoteRow{date_label, weekday, download_token
  (alias downloadToken), segment_badge}` — carries the opaque token, NOT
  file_id (FLAG A baked into the frozen wire). `NoteListCard`, `FileCard`
  (no file_id/url fields), `ErrorBubble{code,text,chips}`, `Calendar`,
  `Bubble`, `ChipRow`, `Chip/ChipAction/ChipActionKind`.
- Errors `app/contracts/errors.py`: `ErrorCode{E_NODATA,E_YEAR,E_TIMEOUT,
  E_FETCH,E_UNKNOWN}`. E_NODATA default copy is tax-flavored → CN overrides
  `text` with the "only generated for days you traded" explainer (proposal §What).
- Config `app/config/defaults.py`: `Limits.contract_note_page_size=10`,
  `note_narrow_threshold=50`; `calendar_bounds[report_contract_notes] =
  DateWindow(floor=2018-01-01, cap_relative_days=0)` (cap today, no max range).
- Flow `app/contracts/flow.py`: `FlowSpec` Protocol (intent/config/steps()),
  `FLOW_ATTR="FLOW"`, `ByteValidation(min_bytes=1024, pdf_magic=b"%PDF",
  silent_retries=1)`, `Step/StepKind/StepState`, `FlowConfig/DateWindow`.
- `app/flows/__init__.py` MISSING in this worktree — EXPECTED: it is
  engine-owned (flow-engine-runtime, change 2), lands at integration. Not a
  blocked frozen surface; `app.flows.contract_notes` imports fine as a
  namespace subpackage (verified). Not creating it (frozen/engine-owned).

## Design decisions

- Module is a self-contained `ContractNoteFlow` (satisfies `FlowSpec`), driven
  by the engine at integration; here it owns the full CN logic against the
  frozen `FinXClient` protocol + a fake driver in tests.
- **FLAG A token vault:** `DownloadTokenVault` maps opaque `secrets.token_urlsafe`
  tokens → `ContractNote`, partitioned by `session_id` (session-scoped). file_id
  lives ONLY in the vault; rows carry the token; download resolves token→note
  server-side and calls the api. adapter with `client_code = session.user_id`.
  FlowState (frozen) has no map slot, so the vault is the server-side store.
- client_id/client_code are ALWAYS `session.user_id`; the flow API has NO
  parameter that accepts a user-supplied client_id/file_id (structural FLAG A).
- Email send has no CN endpoint in the frozen contract → the flow SURFACES the
  email chips + renders a masked-email confirmation (`email_confirmation`,
  masked address passed in by the orchestrator); actual send is orchestrator-owned.
- Tests authored from the proposal's done-condition/guarantees (not from impl);
  the mandated fresh spec-verifier panel is the independent from-spec check.
- Fixtures: reuse read-only `contract_note_list_success.json` /
  `contract_note_204_no_data.json`; build single-note / dual-note-MCX / >50 /
  raw-PDF-byte cases INLINE in the test file (stay within the two-file manifest;
  no writes to the shared fixtures dir).

## Task log

- **T1 (scaffold)** — DONE. tasks.md + loop.md written. (this commit)
- **T2 (flow module)** — pending.
- **T3 (tests)** — pending.
- **T4 (spec harness + verifier panel)** — pending.
- **T5 (ship)** — pending.

## Verifier rounds

- none yet.

## Open questions / carried-forward [CONFIRM]

- Dual-note day (Grp1+MCX same date) is UNOBSERVED (proposal §Impact) — segment
  badge path implemented to the design assumption; flagged for verification.
- EC-3 "today's note" publish-time is [OPEN] in the proposal; cap = today
  (cap_relative_days=0) per remote-config; not further constrained here.
