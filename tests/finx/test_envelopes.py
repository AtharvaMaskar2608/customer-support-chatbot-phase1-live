"""Envelope-parser spec tests (specs/finx-client §Three response-envelope parsers).

Every parser outcome (success / no_data / auth_error) is exercised against a
sanitized capture fixture. Also asserts: no-data is reason-SET based (both
wordings), the brokerage hybrid is parsed by the .NET parser on Status, the
empty-string Response is tolerated, and 401 is an auth error regardless of body.
"""

from __future__ import annotations

from app.finx.envelopes import (
    NO_DATA_REASONS,
    Outcome,
    parse_dotnet_envelope,
    parse_go_envelope,
    parse_mis_envelope,
)

from tests.finx.conftest import load


# --- .NET parser ---


def test_dotnet_pnl_download_success():
    env = parse_dotnet_envelope(load("pnl_download_success.json"))
    assert env.outcome is Outcome.success
    assert isinstance(env.payload, str) and env.payload.endswith(".pdf")


def test_dotnet_pnl_email_success_polymorphic_response():
    # Response is a human-readable confirmation string, not a URL.
    env = parse_dotnet_envelope(load("pnl_email_success.json"))
    assert env.outcome is Outcome.success
    assert "mail sent successfully" in env.payload


def test_dotnet_no_data_reason_set_not_literal():
    # "Data not found." AND "Data not available." both classify as no_data.
    found = parse_dotnet_envelope(load("pnl_no_data.json"))
    available = parse_dotnet_envelope(load("tax_failure.json"))
    assert found.outcome is Outcome.no_data
    assert available.outcome is Outcome.no_data
    assert found.reason != available.reason  # different wording, same outcome
    assert {found.reason, available.reason} <= NO_DATA_REASONS


def test_dotnet_401_auth_error_empty_string_response():
    body = load("dotnet_401.json")
    # Empty-string Response must be tolerated (not assumed str|null only).
    assert body["Response"] == ""
    env = parse_dotnet_envelope(body, http_status=401)
    assert env.outcome is Outcome.auth_error


def test_brokerage_hybrid_parsed_on_status():
    body = load("brokerage_hybrid_success.json")
    # Hybrid: both StatusCode and Status present.
    assert "StatusCode" in body and "Status" in body
    env = parse_dotnet_envelope(body)
    assert env.outcome is Outcome.success
    # Response array of segment groups exposed intact.
    assert isinstance(env.payload, list)
    assert env.payload[0]["title"] == "Equity"


def test_dotnet_ledger_success_and_no_data():
    assert parse_dotnet_envelope(load("ledger_pdf_success.json")).outcome is Outcome.success
    assert parse_dotnet_envelope(load("ledger_no_data.json")).outcome is Outcome.no_data


# --- Go parser ---


def test_go_contract_list_success():
    env = parse_go_envelope(load("contract_note_list_success.json"))
    assert env.outcome is Outcome.success
    assert "contractNotes" in env.payload


def test_go_204_no_data_empty_body():
    env = parse_go_envelope(load("contract_note_204_no_data.json"))
    assert env.outcome is Outcome.no_data
    assert env.payload == {}


# --- MIS parser ---


def test_mis_cml_success():
    env = parse_mis_envelope(load("cml_success.json"))
    assert env.outcome is Outcome.success
    assert "cmlLink" in env.payload


def test_mis_401_auth_error():
    # Detected by HTTP 401 even though the MIS 401 body differs from .NET's.
    env = parse_mis_envelope(load("mis_401.json"), http_status=401)
    assert env.outcome is Outcome.auth_error
    # And the body-level statusCode:401 is also treated as auth_error defensively.
    env2 = parse_mis_envelope(load("cml_401.json"))
    assert env2.outcome is Outcome.auth_error


def test_business_failure_returns_http_200_branch_on_body():
    # A 200-with-Fail body branches on the envelope, not HTTP status.
    env = parse_dotnet_envelope(load("pnl_no_data.json"), http_status=200)
    assert env.outcome is Outcome.no_data
