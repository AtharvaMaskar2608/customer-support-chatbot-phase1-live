"""Intent/status → Freshdesk field mapping, asserted against the proposal.

Proposal: Jini query types map to the Freshdesk Type values that EXIST in the
account (REPORTS / CONTRACT NOTES / CHARGES / LOGIN / TRADE AND ORDER /
GENERAL QUERY / KYC); the cascade stays pinned; status enum → user copy
(2 Open / 3 Pending / 4 Resolved / 5 Closed).
"""

from __future__ import annotations

from app.contracts.router import Intent
from app.ticketing.mapping import (
    freshdesk_type_for_intent,
    status_copy,
    subject_sub_type_for_intent,
)

#: The Type values that exist in the account (04 §0). The mapping may only emit
#: these (an unprovisioned Type value → Freshdesk 400).
ALLOWED_TYPES = {
    "REPORTS",
    "CONTRACT NOTES",
    "CHARGES",
    "LOGIN",
    "TRADE AND ORDER",
    "GENERAL QUERY",
    "KYC",
}


def test_every_intent_maps_to_an_allowed_type(config):
    for intent in Intent:
        value = freshdesk_type_for_intent(intent, config)
        assert value in ALLOWED_TYPES, f"{intent} → {value!r} not an account Type"


def test_specific_type_mappings(config):
    assert freshdesk_type_for_intent(Intent.report_pnl, config) == "REPORTS"
    assert freshdesk_type_for_intent(Intent.report_contract_notes, config) == "CONTRACT NOTES"
    assert freshdesk_type_for_intent(Intent.report_brokerage, config) == "CHARGES"


def test_send_type_toggle_off_returns_none(config):
    """send_type:false reverts to the test-ticket behaviour (Type null)."""
    config.type_map.send_type = False
    assert freshdesk_type_for_intent(Intent.report_pnl, config) is None


def test_mapping_accepts_intent_or_str(config):
    assert freshdesk_type_for_intent("report_pnl", config) == "REPORTS"


def test_subject_sub_type_is_human_readable(config):
    assert subject_sub_type_for_intent(Intent.report_pnl, config) == "P&L"
    assert subject_sub_type_for_intent(Intent.report_cml, config) == "CML"
    # falls back to the configured default for a non-report intent
    assert subject_sub_type_for_intent(Intent.smalltalk_fallback, config) == "General Query"


def test_status_copy_maps_the_enum():
    assert status_copy(2) == "Open"
    assert status_copy(3) == "Pending"
    assert status_copy(4) == "Resolved"
    assert status_copy(5) == "Closed"


def test_status_copy_never_leaks_raw_int():
    # Unknown status renders as a word, never the raw enum int.
    assert status_copy(99) == "Unknown"
    assert status_copy(None) == "Unknown"
