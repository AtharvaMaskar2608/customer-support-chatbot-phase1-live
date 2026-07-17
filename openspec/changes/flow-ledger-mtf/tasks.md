# Tasks — flow-ledger-mtf

Vertical slice: the self-contained Ledger / MTF-Ledger flow module. Two files
only (`app/flows/ledger.py`, `tests/flows/test_ledger.py`). Builds against frozen
contracts; adapters + byte-fetch faked in tests. No live API.

- [ ] 1. Scaffold: `tasks.md` + `loop.md` (this commit).
- [ ] 2. Implement `app/flows/ledger.py`:
  - [ ] 2.1 `LedgerFlow` satisfying the frozen `FlowSpec` (module-level `FLOW`);
        primary `intent = report_ledger`, MTF served via the report-type step
        (additive `intents` hint for the discovery registry).
  - [ ] 2.2 `FlowConfig` window: floor 2019-01-01, cap today+7, **no** max-range
        clamp; `steps()` = report_type → date_range → delivery → generate.
  - [ ] 2.3 `LedgerPdfRequest` builder: `LoginId`=client code (not "JIFFY"),
        `Group`="GROUP1", `Margin` 0/1 per report type, `RequestFor` 0/1 per branch.
  - [ ] 2.4 Date presets (resolved dates), out-of-window nudge (Jan 2019 floor),
        future clamp confirm (today+7).
  - [ ] 2.5 Generation/delivery driver: download (server-side fetch + byte
        validation + one silent retry) and email (masked address); URL/file_id
        never surfaced or logged.
  - [ ] 2.6 Error mapping: E-NODATA (ledger copy) / MTF plain no-data / E-FETCH
        (ledger copy, after failed retry) / E-TIMEOUT / E-UNKNOWN / session-expiry.
  - [ ] 2.7 Friendly filename `Ledger_<range>.pdf` / `MTF_Ledger_<range>.pdf`, no
        password line.
- [ ] 3. Write `tests/flows/test_ledger.py` FROM THE PROPOSAL (both report types →
      correct request; E-* mappings; window enforcement; MTF behind [CONFIRM];
      filename; email masking; no URL leak).
- [ ] 4. Run `testCommand` + `doneCondition`; fix until green.
- [ ] 5. Fresh spec-verifier (all 3 lenses); fix; ship.

## [CONFIRM] items carried VERBATIM (never resolved here)

- `Margin:1` = MTF unverified (byte-identical on the no-MTF test account).
- `RequestFor:1` email branch untested (no email branch captured).
- `Group` "GROUP1" case-sensitivity unconfirmed.
- Ledger date-window cap today+7 [CONFIRM].
