"""FinX model spec tests (specs/finx-client §Per-endpoint identity traps + models).

Asserts the inconsistent-by-design identity fields, the per-endpoint RequestFor /
FileFormat semantics, the With_Exp int-vs-bool split, contract-note rows keyed by
file_id, and the [CONFIRM]/[GAP] markers.
"""

from __future__ import annotations

from app.finx.envelopes import parse_dotnet_envelope, parse_go_envelope, parse_mis_envelope
from app.finx.models import (
    ENDPOINTS,
    BrokerageGroup,
    CmlBody,
    ContractNoteListBody,
    GetDetailedPNLRequest,
    GetGlobalPNLNewRequest,
    GetLedgerDetailsRequest,
    GlobalPnlNewObject,
    LedgerPdfRequest,
    PnlPdfRequest,
)

from tests.finx.conftest import load


def test_ledger_identity_differs_data_vs_pdf():
    # PDF endpoint: LoginId = client code, Group = "GROUP1" (uppercase).
    pdf = LedgerPdfRequest(
        ClientId="X008593", LoginId="X008593", FromDate="2026-07-01",
        ToDate="2026-07-22", SessionId="<s>",
    )
    assert pdf.LoginId == "X008593"
    assert pdf.Group == "GROUP1"
    assert pdf.Margin == 0
    # Data endpoint: LoginId = "JIFFY", Group = "Group1".
    data = GetLedgerDetailsRequest(ClientId="X008593", FromDate="a", ToDate="b", SessionId="<s>")
    assert data.LoginId == "JIFFY"
    assert data.Group == "Group1"


def test_detailed_pnl_userid_literal():
    d = GetDetailedPNLRequest(ClientId="X008593", FromDate="a", ToDate="b", SessionId="<s>")
    assert d.UserId == "neuron"


def test_with_exp_int_vs_bool():
    # PDF endpoint uses a boolean With_Exp; the data endpoint uses an int.
    pdf = PnlPdfRequest(
        ClientId="X1", UserId="X1", Group="Cash", FromDate="a", ToDate="b",
        RequestFor=0, SessionId="<s>",
    )
    assert pdf.With_Exp is True and isinstance(pdf.With_Exp, bool)
    data = GetGlobalPNLNewRequest(
        UserId="X1", ClientId="X1", Group="Cash", FromDate="a", ToDate="b", SessionId="<s>",
    )
    assert data.With_Exp == 1 and isinstance(data.With_Exp, int) and not isinstance(data.With_Exp, bool)


def test_request_for_forks_by_endpoint():
    # PNL/Ledger PDF download = 0; Tax download = 2; email = 1 on all.
    assert ENDPOINTS["GetGlobalPNLPDF"].request_for_download == 0
    assert ENDPOINTS["GetLedgerDetailsPDF"].request_for_download == 0
    assert ENDPOINTS["GetTaxReportPDF"].request_for_download == 2
    for name in ("GetGlobalPNLPDF", "GetLedgerDetailsPDF", "GetTaxReportPDF"):
        assert ENDPOINTS[name].request_for_email == 1
    # FileFormat 1=PDF, 2=Excel (Tax only).
    assert ENDPOINTS["GetTaxReportPDF"].file_format == {"pdf": 1, "excel": 2}


def test_confirm_and_gap_markers_present():
    # MTF Margin:1 marked [CONFIRM] on the ledger PDF endpoint.
    ledger = ENDPOINTS["GetLedgerDetailsPDF"]
    assert any("Margin:1" in c for c in ledger.confirm)
    # Blocked flows carry a [GAP] note.
    assert ENDPOINTS["GetDetailedPNL"].blocked is True
    assert ENDPOINTS["GetDetailedPNL"].gap
    assert ENDPOINTS["Holdings"].blocked is True
    assert any("FINX" in c for c in ENDPOINTS["Holdings"].confirm)


def test_contract_notes_keyed_by_file_id():
    env = parse_go_envelope(load("contract_note_list_success.json"))
    body = ContractNoteListBody.model_validate(env.payload)
    keyed = body.by_file_id()
    # Keyed by file_id, not id; id is redundant (== date).
    assert set(keyed.keys()) == {n.file_id for n in body.contractNotes}
    for note in body.contractNotes:
        assert note.id == note.date  # redundant field
    assert "<FILE_ID_TOKEN>" in keyed


def test_global_pnl_new_object_shape():
    env = parse_dotnet_envelope(load("global_pnl_new_object.json"))
    obj = GlobalPnlNewObject.model_validate(env.payload)
    assert obj.Trades and obj.Expenses
    # Falsy With_Exp fixture is a bare array (not an object).
    falsy = parse_dotnet_envelope(load("global_pnl_new_falsy_array.json"))
    assert isinstance(falsy.payload, list)


def test_brokerage_and_cml_response_models():
    env = parse_dotnet_envelope(load("brokerage_hybrid_success.json"))
    groups = [BrokerageGroup.model_validate(g) for g in env.payload]
    assert groups[0].title == "Equity"
    # desc rendered verbatim (pre-formatted rate text).
    assert groups[0].list[0].desc == "₹0.10 for trade value of 10 thousand"

    cml = parse_mis_envelope(load("cml_success.json"))
    body = CmlBody.model_validate(cml.payload)
    assert body.cmlLink.startswith("https://onmedia.choiceindia.com/")
