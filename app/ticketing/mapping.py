"""Intent / status → Freshdesk field mapping (config-driven).

Maps the router's ``Intent`` onto the account's ``ticket_type`` (Type) values and
onto the human-readable sub-type label used in the subject line, and maps the
Freshdesk status enum onto user-facing copy. Every value comes from
``freshdesk.yaml`` — nothing here is hardcoded per 04 §5.
"""

from __future__ import annotations

from app.contracts.router import Intent
from app.ticketing.config import FreshdeskConfig

#: Freshdesk status enum → user copy (04 §5: 2 Open / 3 Pending / 4 Resolved /
#: 5 Closed). These are Freshdesk protocol semantics, not swappable field values.
STATUS_COPY: dict[int, str] = {
    2: "Open",
    3: "Pending",
    4: "Resolved",
    5: "Closed",
}


def _intent_key(intent: Intent | str) -> str:
    """Normalize an Intent (enum or its string value) to its lookup key."""
    return intent.value if isinstance(intent, Intent) else str(intent)


def freshdesk_type_for_intent(intent: Intent | str, config: FreshdeskConfig) -> str | None:
    """The Freshdesk ``type`` (Type) value for an Intent, or ``None`` when the
    config has ``send_type: false`` (reverts to the test-ticket behaviour of a
    null Type). Unmapped intents fall back to the configured default."""
    if not config.type_map.send_type:
        return None
    return config.type_map.by_intent.get(_intent_key(intent), config.type_map.default)


def subject_sub_type_for_intent(intent: Intent | str, config: FreshdeskConfig) -> str:
    """The human-readable sub-type label for the subject line (distinct from the
    pinned cascade value ``cf_query_sub_type=finx-bot-test``)."""
    return config.subject_sub_type.by_intent.get(
        _intent_key(intent), config.subject_sub_type.default
    )


def status_copy(status: int) -> str:
    """Map a Freshdesk status enum int to user copy; unknown values render as
    ``Unknown`` (never a raw enum int) so status cards stay human-readable."""
    return STATUS_COPY.get(status, "Unknown")
