"""Freshdesk ticket-payload assembly (04 §5 field map).

Builds the exact ``POST /api/v2/tickets`` body from a ``SessionContext`` + an
``Intent`` + the conversation transcript, reading every Freshdesk value from
config. The description is HTML (Freshdesk renders it as HTML), so all user
content is escaped (``< > & "``) before it is wrapped in ``<p>`` per turn, plus a
metadata block (ClientID, query type, language, timestamp, turn count — K3).

Hard rule (spec §2.6): the requester ClientID is ALWAYS ``session.user_id``;
there is no user-supplied client-id parameter here, so a Contract-Note-style
spoofed id cannot reach Freshdesk.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from app.contracts.router import Intent
from app.contracts.wire import SessionContext
from app.ticketing.config import FreshdeskConfig
from app.ticketing.mapping import freshdesk_type_for_intent, subject_sub_type_for_intent


class TranscriptTurn(BaseModel):
    """One ordered conversation turn. Ticketing-owned (no frozen
    ``ConversationTranscript`` type exists in contracts-foundation)."""

    model_config = ConfigDict(extra="forbid")

    role: str  # "user" | "assistant"
    content: str


#: The transcript the orchestrator hands to ``raise_ticket``.
ConversationTranscript = list[TranscriptTurn]


def _esc(text: str) -> str:
    """HTML-escape user content for the Freshdesk HTML body (escapes & < > " ')."""
    return html.escape(text, quote=True)


def render_transcript_html(transcript: ConversationTranscript, last_n: int) -> str:
    """Render the most-recent ``last_n`` turns as one ``<p>`` per turn, escaped."""
    turns = transcript[-last_n:] if last_n > 0 else list(transcript)
    lines = [
        f"<p><strong>{_esc(turn.role)}:</strong> {_esc(turn.content)}</p>"
        for turn in turns
    ]
    return "\n".join(lines)


def build_metadata_html(
    *,
    client_id: str,
    query_type: Intent | str,
    language: str,
    raised_at: datetime,
    turns_included: int,
    turns_total: int,
) -> str:
    """The metadata block appended to the transcript (all values escaped)."""
    qt = query_type.value if isinstance(query_type, Intent) else str(query_type)
    rows = [
        f"<li>Client ID: {_esc(client_id)}</li>",
        f"<li>Query type: {_esc(qt)}</li>",
        f"<li>Language: {_esc(language)}</li>",
        f"<li>Raised at: {_esc(raised_at.isoformat())}</li>",
        f"<li>Turns included: {turns_included} of {turns_total}</li>",
    ]
    return (
        "<hr>\n<p><strong>Conversation metadata</strong></p>\n<ul>\n"
        + "\n".join(rows)
        + "\n</ul>"
    )


def build_description(
    *,
    session: SessionContext,
    query_type: Intent | str,
    transcript: ConversationTranscript,
    language: str,
    config: FreshdeskConfig,
    raised_at: datetime,
) -> str:
    """The full HTML ``description``: escaped transcript + metadata block."""
    last_n = config.defaults.transcript_last_n
    included = min(len(transcript), last_n) if last_n > 0 else len(transcript)
    body = render_transcript_html(transcript, last_n)
    meta = build_metadata_html(
        client_id=session.user_id,
        query_type=query_type,
        language=language,
        raised_at=raised_at,
        turns_included=included,
        turns_total=len(transcript),
    )
    return f"{body}\n{meta}" if body else meta


def build_ticket_payload(
    *,
    session: SessionContext,
    query_type: Intent,
    transcript: ConversationTranscript,
    language: str,
    config: FreshdeskConfig,
    now: datetime | None = None,
) -> dict:
    """Build the exact 04 §5 ``POST /api/v2/tickets`` body.

    ClientID is derived from ``session.user_id`` only. ``email`` is omitted
    because it is not resolvable from the session and unvalidated emails would
    auto-create junk contacts (04 §6); ``unique_external_id`` alone satisfies the
    "exactly one requester identity" rule.
    """
    raised_at = now or datetime.now(timezone.utc)
    client_id = session.user_id
    cf = config.custom_fields
    d = config.defaults

    sub_type_label = subject_sub_type_for_intent(query_type, config)
    subject = d.subject_template.format(query_sub_type=sub_type_label, client_id=client_id)

    lang_tag = d.language_tag_template.format(language=language)
    tags = [*d.tags, lang_tag]

    payload: dict = {
        "unique_external_id": client_id,
        "name": client_id,  # client name unavailable from the session → ClientID
        "subject": subject,
        "description": build_description(
            session=session,
            query_type=query_type,
            transcript=transcript,
            language=language,
            config=config,
            raised_at=raised_at,
        ),
        "status": d.status,
        "priority": d.priority,
        "source": d.source,
        "group_id": d.group_id,
        "tags": tags,
        "custom_fields": {
            cf.client_id_field: client_id,
            cf.product_field: cf.product,
            cf.query_type_field: cf.query_type,
            cf.query_sub_type_field: cf.query_sub_type,
            cf.source_field: cf.source_value,
        },
    }

    ticket_type = freshdesk_type_for_intent(query_type, config)
    if ticket_type is not None:
        payload["type"] = ticket_type

    return payload
