"""build_ticket_payload asserted against the 04 §5 field map (proposal).

The proposal's doneCondition: raise_ticket builds the EXACT 04 §5 payload from a
SessionContext + Intent + transcript. These tests pin that field map, the
HTML-escaping of user content, and the hard rule that ClientID comes from the
session only (spec §2.6).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.contracts.router import Intent
from app.ticketing.payload import (
    TranscriptTurn,
    build_ticket_payload,
    render_transcript_html,
)

NOW = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)


def _payload(session, config, intent=Intent.report_pnl, transcript=None, language="en"):
    transcript = transcript or [
        TranscriptTurn(role="user", content="where is my P&L?"),
        TranscriptTurn(role="assistant", content="Let me pull that up."),
    ]
    return build_ticket_payload(
        session=session,
        query_type=intent,
        transcript=transcript,
        language=language,
        config=config,
        now=NOW,
    )


def test_exact_04_section5_field_map(session, config):
    p = _payload(session, config)
    assert p["unique_external_id"] == "X008593"
    assert p["name"] == "X008593"  # client name unavailable → ClientID
    assert p["subject"] == "[Choice Jini] P&L — Client X008593"
    assert p["status"] == 2
    assert p["priority"] == 2
    assert p["source"] == 7
    assert p["group_id"] == 22000168676
    assert p["type"] == "REPORTS"
    assert p["tags"] == ["choice-jini", "chatbot-testing", "lang:en"]
    assert p["custom_fields"] == {
        "cf_client_id": "X008593",
        "cf_product": "finx",
        "cf_query_type149508": "finx-bot",
        "cf_query_sub_type": "finx-bot-test",
        "cf_source": "chat box",
    }


def test_client_id_comes_only_from_session(session, config):
    """There is no user-supplied client-id parameter; both the requester id and
    the cf_client_id come from session.user_id (spec §2.6 session-gate)."""
    p = _payload(session, config)
    assert p["unique_external_id"] == session.user_id
    assert p["custom_fields"]["cf_client_id"] == session.user_id


def test_session_secrets_never_appear_in_payload(session, config):
    blob = json.dumps(_payload(session, config))
    assert "SESSION-SECRET" not in blob
    assert "JWT-SECRET" not in blob


def test_language_tag_reflects_language(session, config):
    p = _payload(session, config, language="hinglish")
    assert "lang:hinglish" in p["tags"]


def test_description_escapes_user_content(session, config):
    hostile = TranscriptTurn(role="user", content='<script>alert(1)</script> & "quotes"')
    p = _payload(session, config, transcript=[hostile])
    desc = p["description"]
    assert "<script>" not in desc
    assert "&lt;script&gt;" in desc
    assert "&amp;" in desc
    assert "&quot;" in desc


def test_description_has_one_p_per_turn_plus_metadata(session, config):
    p = _payload(session, config)
    desc = p["description"]
    assert desc.count("<p><strong>") >= 2  # one per turn
    assert "Conversation metadata" in desc
    assert "Client ID: X008593" in desc
    assert "Query type: report_pnl" in desc
    assert "Language: en" in desc


def test_type_omitted_when_send_type_off(session, config):
    config.type_map.send_type = False
    p = _payload(session, config)
    assert "type" not in p


def test_transcript_is_bounded_by_last_n(session, config):
    config.defaults.transcript_last_n = 2
    turns = [TranscriptTurn(role="user", content=f"msg {i}") for i in range(5)]
    p = _payload(session, config, transcript=turns)
    desc = p["description"]
    assert "msg 4" in desc and "msg 3" in desc  # last two kept
    assert "msg 0" not in desc  # older trimmed
    assert "Turns included: 2 of 5" in desc


def test_render_transcript_last_n_zero_renders_all(config):
    turns = [TranscriptTurn(role="user", content=f"m{i}") for i in range(3)]
    html = render_transcript_html(turns, last_n=0)
    assert html.count("<p>") == 3


def test_subject_uses_human_sub_type_for_each_flow(session, config):
    p = build_ticket_payload(
        session=session,
        query_type=Intent.report_cml,
        transcript=[TranscriptTurn(role="user", content="cml")],
        language="en",
        config=config,
        now=NOW,
    )
    assert p["subject"] == "[Choice Jini] CML — Client X008593"
