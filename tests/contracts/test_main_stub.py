"""Chat-endpoint stub tests (chat-wire-api, task 9.1).

Asserts the POST /api/chat session-seed response is schema-valid: it mints a
thread_id, returns ordered blocks (greeting bubble + starter chips), and carries a
config_slice — with no live FinX/DB calls. Also checks server-only config is never
in the slice.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.contracts.wire import ChatResponse, EntrySurface, SessionContext

client = TestClient(app)


def _session_payload(page: str = "support") -> dict:
    # A widget sends session_id/access_token in the request (they are needed
    # server-side); SessionContext.exclude only strips them from RESPONSES, so
    # the inbound payload must include them explicitly.
    ctx = SessionContext.from_url_params(
        userId="X008593",
        sessionId="s-secret",
        accessToken="jwt-secret",
        isDarkTheme="false",
        platform="web",
        page=page,
    )
    return {
        "user_id": ctx.user_id,
        "session_id": ctx.session_id,
        "access_token": ctx.access_token,
        "is_dark_theme": ctx.is_dark_theme,
        "platform": ctx.platform,
        "page": ctx.page,
        "entry_surface": ctx.entry_surface.value,
    }


def _seed_request(page: str = "support") -> dict:
    return {"session": _session_payload(page), "turn_number": 0}


def test_session_seed_is_schema_valid():
    resp = client.post("/api/chat", json=_seed_request())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Re-validates against the wire contract.
    parsed = ChatResponse.model_validate(body)

    # First turn mints a thread_id.
    assert parsed.thread_id
    # Ordered blocks: greeting bubble first, then a chip row.
    assert [b.type for b in parsed.blocks] == ["bubble", "chip_row"]
    assert parsed.blocks[0].compliance_footer is True
    assert parsed.blocks[0].text  # greeting text present
    # Session-seed carries a config_slice.
    assert parsed.config_slice is not None
    assert len(parsed.config_slice.entry_chips) == 4
    assert "{client_id}" not in parsed.config_slice.greeting
    assert "X008593" in parsed.config_slice.greeting
    # Caps reported.
    assert parsed.caps.messages_cap == 10
    # No intent on the seed.
    assert parsed.intent is None


def test_config_slice_excludes_server_only_config():
    body = client.post("/api/chat", json=_seed_request()).json()
    blob = str(body["config_slice"])
    for forbidden in ("rag_candidate_k", "rrf_k", "reranker", "calendar_bounds", "freshdesk"):
        assert forbidden not in blob


def test_secrets_not_echoed_in_response():
    body = client.post("/api/chat", json=_seed_request()).text
    assert "s-secret" not in body
    assert "jwt-secret" not in body


def test_reports_entry_surface_uses_reports_chips():
    payload = _session_payload(page="reports")
    assert payload["entry_surface"] == EntrySurface.reports.value
    body = client.post("/api/chat", json={"session": payload, "turn_number": 0}).json()
    labels = [c["label"] for c in body["config_slice"]["entry_chips"]]
    assert "📁 Holding Statement" in labels  # reports-entry chip
