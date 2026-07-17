"""Contract Note flow tests — asserted against the flow-contract-notes proposal
(done-condition + §Contracts/§What Changes), NOT against the implementation.

Coverage maps to the proposal's promised behavior:
- discovery / registration (module-level ``FLOW`` satisfying ``FlowSpec``);
- the list call uses the SESSION ``client_id`` (FLAG A), snake_case, no SessionId;
- branch on the body ``StatusCode``: 204 / 1-note / 2+-note / >threshold-nudge;
- note-list keyed by ``file_id`` but carrying only an opaque ``downloadToken``,
  with dual-note segment badges;
- per-note download validates raw PDF bytes, one silent retry then E-FETCH,
  timeout → E-TIMEOUT;
- ``file_id`` is never on the wire nor logged; the token is session-scoped;
- per-flow calendar bounds (floor 2018-01-01 / cap today / no max range);
- the email-all confirmation (single + bulk).

The FinX driver is a local fake satisfying the frozen ``FinXClient.go`` protocol
(the real adapters are a parallel change). Standard fixtures are reused read-only;
scenario bodies (single / dual-note MCX / >threshold) and raw-PDF byte payloads
are built inline to stay within the two-file manifest.
"""

from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace

import pytest

from app.contracts.errors import ErrorCode
from app.contracts.flow import FLOW_ATTR, FlowSpec
from app.contracts.router import Intent
from app.finx.envelopes import Outcome, parse_go_envelope
from app.finx.models import ContractNote
from app.flows.contract_notes import (
    FLOW,
    ContractNoteFlow,
    DownloadTokenVault,
)

from tests.finx.conftest import load

# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


def _session(user_id: str = "X008593", session_id: str = "sess-A"):
    """A minimal authenticated session (only user_id + session_id are read)."""
    return SimpleNamespace(user_id=user_id, session_id=session_id)


def _go_success(notes: list[dict]):
    return parse_go_envelope(
        {
            "StatusCode": 200,
            "Message": "Success",
            "DevMessage": None,
            "Body": {"client_code": "IGNORED_BODY_CODE", "contractNotes": notes},
        }
    )


def _note(date_: str, file_id: str, group: str = "Grp1", invoice: str = "1") -> dict:
    return {"date": date_, "file_id": file_id, "group": group, "id": date_, "invoice_number": invoice}


def _pdf(n: int = 3000) -> bytes:
    return b"%PDF-1.4" + b"0" * (n - 8)


_BAD_SHORT = b"%PDF" + b"0" * 10  # valid magic, below the 1024-byte floor
_BAD_MAGIC = b"NOTPDF" + b"0" * 4000  # big enough, wrong magic


class _FakeGo:
    """Fake ``GoMiddlewareAdapter``: records requests, replays canned results."""

    def __init__(self, list_result=None, downloads=None):
        self._list_result = list_result
        self._downloads = list(downloads or [])
        self.list_requests: list = []
        self.download_requests: list = []

    async def list_contract_notes(self, req):
        self.list_requests.append(req)
        if isinstance(self._list_result, Exception):
            raise self._list_result
        return self._list_result

    async def download_contract_note(self, req):
        self.download_requests.append(req)
        result = self._downloads.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def get_brokerage_slab(self, req):  # unused by this flow
        raise AssertionError("brokerage not exercised by the CN flow")


class _FakeFinX:
    def __init__(self, go: _FakeGo):
        self.go = go


def _flow_with(go: _FakeGo, **kw):
    return ContractNoteFlow(**kw), _FakeFinX(go)


# ---------------------------------------------------------------------------
# Discovery / registration
# ---------------------------------------------------------------------------


def test_flow_module_registration_contract():
    # Discovered by module presence: a module-level FLOW satisfying FlowSpec.
    assert FLOW_ATTR == "FLOW"
    assert isinstance(FLOW, FlowSpec)
    assert FLOW.intent is Intent.report_contract_notes
    kinds = [s.kind.value for s in FLOW.steps()]
    assert "date_range" in kinds  # the one user-collected step


def test_calendar_window_bounds():
    # Per-flow window: floor 2018-01-01, cap today (no +7), no max range.
    assert FLOW.config.window.floor == date(2018, 1, 1)
    assert FLOW.config.window.cap_relative_days == 0
    assert FLOW.config.window.max_range_years is None
    cal = FLOW.calendar(today=date(2024, 9, 17))
    assert cal.min_date == date(2018, 1, 1)
    assert cal.max_date == date(2024, 9, 17)  # cap == today
    assert cal.max_range_days is None  # no max range


def test_date_range_presets_resolve_dates():
    blocks = FLOW.date_range_step(today=date(2024, 9, 17))  # a Tuesday
    chips = blocks[0].chips
    assert [c.label for c in chips][:3] == ["Last trading day", "Last 7 days", "This month"]
    # Presets carry resolved from/to dates; custom opens the calendar.
    assert chips[0].action.payload == {"from": "2024-09-17", "to": "2024-09-17"}
    assert chips[3].action.kind.value == "open_calendar"


def test_last_trading_day_skips_weekend():
    # 2024-09-15 is a Sunday → last trading day rolls back to Friday the 13th.
    ltd = FLOW.date_range_step(today=date(2024, 9, 15))[0].chips[0].action.payload
    assert ltd == {"from": "2024-09-13", "to": "2024-09-13"}


# ---------------------------------------------------------------------------
# FLAG A: session-bound identity on the list call
# ---------------------------------------------------------------------------


async def test_list_call_binds_session_client_id_snake_case():
    go = _FakeGo(_go_success([_note("16092024", "FID1"), _note("17092024", "FID2")]))
    flow, finx = _flow_with(go)
    await flow.fetch(_session(user_id="X008593"), from_date="2024-09-01", to_date="2024-09-30", finx=finx)
    req = go.list_requests[0]
    # client_id is the SESSION user_id — never taken from the request body/user.
    assert req.client_id == "X008593"
    # snake_case request with NO SessionId field (header-only auth is adapter-owned).
    dumped = req.model_dump()
    assert set(dumped) == {"client_id", "from_date", "to_date"}
    assert dumped["from_date"] == "2024-09-01" and dumped["to_date"] == "2024-09-30"


async def test_list_client_id_ignores_user_supplied_identity():
    # Even if the API body echoes a different client_code, the request uses the
    # session user_id; there is no flow parameter that accepts a user client_id.
    go = _FakeGo(_go_success([_note("16092024", "A"), _note("17092024", "B")]))
    flow, finx = _flow_with(go)
    await flow.fetch(_session(user_id="X999"), from_date="a", to_date="b", finx=finx)
    assert go.list_requests[0].client_id == "X999"


# ---------------------------------------------------------------------------
# Branch on body StatusCode: 204 / 1 / 2+ / >threshold
# ---------------------------------------------------------------------------


async def test_branch_204_no_data_explainer():
    go = _FakeGo(parse_go_envelope(load("contract_note_204_no_data.json")))
    flow, finx = _flow_with(go)
    blocks = await flow.fetch(_session(), from_date="a", to_date="b", finx=finx)
    assert [b.type for b in blocks] == ["error_bubble"]
    assert blocks[0].code is ErrorCode.E_NODATA
    # The mandatory CN explainer (not the tax-flavored taxonomy default).
    assert "only generated for the days you actually traded" in blocks[0].text
    assert "FY" not in blocks[0].text


async def test_branch_success_but_empty_list_is_no_data():
    go = _FakeGo(_go_success([]))
    flow, finx = _flow_with(go)
    blocks = await flow.fetch(_session(), from_date="a", to_date="b", finx=finx)
    assert blocks[0].type == "error_bubble" and blocks[0].code is ErrorCode.E_NODATA


async def test_branch_single_note_direct_delivery():
    go = _FakeGo(_go_success([_note("16092024", "FID1")]), downloads=[_pdf()])
    flow, finx = _flow_with(go)
    blocks = await flow.fetch(_session(), from_date="a", to_date="b", finx=finx)
    # One note → skip the list, deliver directly.
    assert [b.type for b in blocks] == ["file_card", "chip_row"]
    assert not any(b.type == "note_list_card" for b in blocks)
    assert go.download_requests[0].client_code == "X008593"


async def test_branch_two_notes_renders_note_list():
    go = _FakeGo(_go_success([_note("16092024", "A"), _note("17092024", "B")]))
    flow, finx = _flow_with(go)
    blocks = await flow.fetch(_session(), from_date="a", to_date="b", finx=finx)
    assert [b.type for b in blocks] == ["note_list_card"]
    card = blocks[0]
    assert card.total == 2
    assert card.page_size == 10  # remote-config contract_note_page_size
    assert len(card.rows) == 2


async def test_branch_over_threshold_narrow_nudge_before_list():
    notes = [_note(f"{d:02d}012024", f"F{d}") for d in range(1, 30)]  # 29 notes
    notes += [_note(f"{d:02d}022024", f"G{d}") for d in range(1, 24)]  # +23 = 52 > 50
    go = _FakeGo(_go_success(notes))
    flow, finx = _flow_with(go)
    blocks = await flow.fetch(_session(), from_date="a", to_date="b", finx=finx)
    # Nudge instead of dumping 52 rows; no note-list card is rendered.
    assert [b.type for b in blocks] == ["bubble", "chip_row"]
    assert not any(b.type == "note_list_card" for b in blocks)
    assert "52" in blocks[0].text
    labels = [c.label for c in blocks[1].chips]
    assert any("Email all 52" in ell for ell in labels)
    assert any("Narrow" in ell for ell in labels)


# ---------------------------------------------------------------------------
# Note-list card: keyed by file_id, opaque token, badges, dividers
# ---------------------------------------------------------------------------


async def test_note_list_keyed_by_file_id_but_token_on_wire():
    go = _FakeGo(_go_success([_note("16092024", "FIDA"), _note("17092024", "FIDB")]))
    flow, finx = _flow_with(go)
    card = (await flow.fetch(_session(), from_date="a", to_date="b", finx=finx))[0]
    # Rows carry an opaque downloadToken, NEVER the file_id.
    tokens = {r.download_token for r in card.rows}
    assert "FIDA" not in tokens and "FIDB" not in tokens
    assert all(len(t) >= 16 for t in tokens)
    # Distinct notes → distinct tokens.
    assert len(tokens) == 2


async def test_dual_note_day_segment_badges():
    # Same trade date, two groups → dual-note day: each row shows its segment.
    go = _FakeGo(
        _go_success([_note("16092024", "EQ", group="Grp1"), _note("16092024", "CO", group="MCX")])
    )
    flow, finx = _flow_with(go)
    card = (await flow.fetch(_session(), from_date="a", to_date="b", finx=finx))[0]
    badges = {r.segment_badge for r in card.rows}
    assert badges == {"Equity & F&O", "Commodity"}


async def test_group_matched_case_insensitively_and_single_day_no_badge():
    # Two distinct single-note days (GRP1 upper on one) → no badge on either.
    go = _FakeGo(_go_success([_note("16092024", "A", group="GRP1"), _note("17092024", "B", group="Grp1")]))
    flow, finx = _flow_with(go)
    card = (await flow.fetch(_session(), from_date="a", to_date="b", finx=finx))[0]
    assert all(r.segment_badge is None for r in card.rows)


async def test_note_list_ordering_and_month_dividers():
    go = _FakeGo(_go_success([_note("05082024", "A"), _note("16092024", "B")]))
    flow, finx = _flow_with(go)
    card = (await flow.fetch(_session(), from_date="a", to_date="b", finx=finx))[0]
    # Newest first.
    assert card.rows[0].date_label == "16 Sep 2024"
    assert card.rows[1].date_label == "05 Aug 2024"
    assert card.month_dividers == ["September 2024", "August 2024"]
    # Footer chips: email-all + change-dates.
    labels = [c.label for c in card.footer_chips]
    assert any("Email all 2" in ell for ell in labels)


async def test_reused_standard_fixture_two_notes():
    # The shared capture fixture (2 Grp1/GRP1 notes) renders a clean 2-row list.
    env = parse_go_envelope(load("contract_note_list_success.json"))
    assert env.outcome is Outcome.success
    go = _FakeGo(env)
    flow, finx = _flow_with(go)
    card = (await flow.fetch(_session(), from_date="a", to_date="b", finx=finx))[0]
    assert card.type == "note_list_card" and card.total == 2


# ---------------------------------------------------------------------------
# Per-note download: validation, one silent retry, timeout
# ---------------------------------------------------------------------------


async def test_download_valid_pdf_file_card():
    go = _FakeGo(None, downloads=[_pdf(200_000)])
    flow, finx = _flow_with(go)
    note = ContractNote(date="16092024", file_id="FID", group="Grp1", id="16092024", invoice_number="1")
    blocks = await flow._deliver_note(_session(), note, finx)
    fc = blocks[0]
    assert fc.type == "file_card" and fc.format == "pdf"
    assert fc.filename == "Contract_Note_2024-09-16.pdf"  # renamed, no Client ID
    assert fc.password_hint is None  # CN PDFs unprotected
    assert len(go.download_requests) == 1  # no retry needed


async def test_download_commodity_note_filename_suffix():
    go = _FakeGo(None, downloads=[_pdf()])
    flow, finx = _flow_with(go)
    note = ContractNote(date="16092024", file_id="FID", group="MCX", id="16092024", invoice_number="1")
    fc = (await flow._deliver_note(_session(), note, finx))[0]
    assert fc.filename == "Contract_Note_2024-09-16_MCX.pdf"


@pytest.mark.parametrize("bad", [_BAD_SHORT, _BAD_MAGIC, b""])
async def test_download_one_silent_retry_then_efetch(bad):
    go = _FakeGo(None, downloads=[bad, bad])
    flow, finx = _flow_with(go)
    note = ContractNote(date="16092024", file_id="FID", group="Grp1", id="16092024", invoice_number="1")
    blocks = await flow._deliver_note(_session(), note, finx)
    assert blocks[0].type == "error_bubble" and blocks[0].code is ErrorCode.E_FETCH
    # Exactly ONE silent retry → exactly two attempts.
    assert len(go.download_requests) == 2


async def test_download_retry_recovers_on_second_attempt():
    go = _FakeGo(None, downloads=[_BAD_SHORT, _pdf()])
    flow, finx = _flow_with(go)
    note = ContractNote(date="16092024", file_id="FID", group="Grp1", id="16092024", invoice_number="1")
    blocks = await flow._deliver_note(_session(), note, finx)
    assert blocks[0].type == "file_card"
    assert len(go.download_requests) == 2  # first failed, retry succeeded silently


async def test_download_timeout_maps_e_timeout():
    go = _FakeGo(None, downloads=[TimeoutError()])
    flow, finx = _flow_with(go)
    note = ContractNote(date="16092024", file_id="FID", group="Grp1", id="16092024", invoice_number="1")
    blocks = await flow._deliver_note(_session(), note, finx)
    assert blocks[0].type == "error_bubble" and blocks[0].code is ErrorCode.E_TIMEOUT


async def test_list_timeout_and_error_mapping():
    flow, finx = _flow_with(_FakeGo(TimeoutError()))
    blocks = await flow.fetch(_session(), from_date="a", to_date="b", finx=finx)
    assert blocks[0].code is ErrorCode.E_TIMEOUT
    flow2, finx2 = _flow_with(_FakeGo(RuntimeError("boom")))
    blocks2 = await flow2.fetch(_session(), from_date="a", to_date="b", finx=finx2)
    assert blocks2[0].code is ErrorCode.E_UNKNOWN


# ---------------------------------------------------------------------------
# FLAG A: file_id never on the wire nor logged; session-scoped token
# ---------------------------------------------------------------------------


async def test_file_id_never_appears_in_rendered_blocks():
    secret = "SUPER_SECRET_FILE_ID_TOKEN_88CHARS"
    go = _FakeGo(_go_success([_note("16092024", secret), _note("17092024", "OTHER_FID")]), downloads=[_pdf()])
    flow, finx = _flow_with(go)
    card = (await flow.fetch(_session(), from_date="a", to_date="b", finx=finx))[0]
    dumped = card.model_dump_json(by_alias=True)
    assert secret not in dumped and "OTHER_FID" not in dumped
    assert "downloadToken" in dumped  # the opaque handle serializes camelCase
    # Downloading via the row's token still delivers, and the file card carries no id.
    token = card.rows[0].download_token
    fc = (await flow.download(_session(), token, finx=_FakeFinX(_FakeGo(None, [_pdf()]))))[0]
    assert secret not in fc.model_dump_json(by_alias=True)


async def test_file_id_never_logged(caplog):
    secret = "LOGGED_FILE_ID_SHOULD_NOT_APPEAR"
    go = _FakeGo(_go_success([_note("16092024", secret), _note("17092024", "B")]), downloads=[_pdf()])
    flow, finx = _flow_with(go)
    with caplog.at_level(logging.DEBUG):
        card = (await flow.fetch(_session(), from_date="a", to_date="b", finx=finx))[0]
        await flow.download(_session(), card.rows[0].download_token, finx=_FakeFinX(_FakeGo(None, [_pdf()])))
    assert secret not in caplog.text


async def test_download_token_is_session_scoped():
    go = _FakeGo(_go_success([_note("16092024", "A"), _note("17092024", "B")]))
    vault = DownloadTokenVault()
    flow = ContractNoteFlow(vault=vault)
    card = (await flow.fetch(_session(session_id="sess-A"), from_date="a", to_date="b", finx=_FakeFinX(go)))[0]
    token = card.rows[0].download_token
    # Same flow/vault but a DIFFERENT session cannot resolve the token → E-FETCH.
    other = _session(user_id="X1", session_id="sess-B")
    blocks = await flow.download(other, token, finx=_FakeFinX(_FakeGo(None, [_pdf()])))
    assert blocks[0].type == "error_bubble" and blocks[0].code is ErrorCode.E_FETCH


async def test_download_uses_session_client_code_not_client_input():
    go = _FakeGo(_go_success([_note("16092024", "FIDA"), _note("17092024", "FIDB")]))
    flow, finx = _flow_with(go)
    card = (await flow.fetch(_session(user_id="X008593"), from_date="a", to_date="b", finx=finx))[0]
    dl_go = _FakeGo(None, [_pdf()])
    await flow.download(_session(user_id="X008593"), card.rows[0].download_token, finx=_FakeFinX(dl_go))
    # client_code is the session user_id; file_id is the vault-resolved value.
    assert dl_go.download_requests[0].client_code == "X008593"
    assert dl_go.download_requests[0].file_id in {"FIDA", "FIDB"}


async def test_unknown_token_yields_efetch():
    flow, finx = _flow_with(_FakeGo(None, [_pdf()]))
    blocks = await flow.download(_session(), "not-a-real-token", finx=finx)
    assert blocks[0].code is ErrorCode.E_FETCH


# ---------------------------------------------------------------------------
# Email branch (single + bulk), masked address
# ---------------------------------------------------------------------------


def test_email_confirmation_single_and_bulk():
    single = FLOW.email_confirmation(masked_email="a***@x.com")
    assert single[0].type == "bubble" and "a***@x.com" in single[0].text
    bulk = FLOW.email_confirmation(masked_email="a***@x.com", count=7)
    assert "7 contract notes" in bulk[0].text
    # No raw PII is constructed here — only the pre-masked address is echoed.
    assert single[1].type == "chip_row"
