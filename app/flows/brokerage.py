"""Brokerage flow — the single-shot rate-slab data card (flow-brokerage).

Brokerage is deliberately **not a stepper flow** (flow spec "Brokerage: This is
not flow. We need to call this API on the intent click or Free Text"): on the
intent it makes one ``get-brokerage-slab`` call and renders the client's rate
slabs as a dynamic data card. There is no date window, no file, no email, and no
computed rupee figure — the API returns pre-formatted rate text that is rendered
VERBATIM, and the actual charge on any trade lives on that day's contract note.

The module self-registers by exposing a module-level ``FLOW`` object satisfying
the frozen ``FlowSpec`` protocol; the engine's importlib discovery loads it by
module presence (no edit to ``app/flows/__init__.py``). Everything here is built
against the frozen contracts only — the real JWT ``go`` adapter and the engine
executor are wired in at runtime.

Two hard product rules (03 §4.6c, flow spec EC-5):
  * render ``desc`` verbatim — never parse or compute a rupee figure;
  * render dynamically — segments and rows-per-segment vary per client, so
    never hardcode the segment set or the row count.
"""

from __future__ import annotations

from typing import Sequence

from pydantic import ValidationError

from app.contracts.errors import ErrorCode
from app.contracts.flow import DateWindow, FlowConfig, Step
from app.contracts.router import Intent
from app.contracts.wire import (
    Bubble,
    Chip,
    ChipAction,
    ChipActionKind,
    ChipRow,
    DataCard,
    DataGroup,
    DataRow,
    ErrorBubble,
    RenderBlock,
)
from app.finx.envelopes import Outcome
from app.finx.interfaces import FinXClient
from app.finx.models import BrokerageGroup, BrokerageSlabRequest

# ---------------------------------------------------------------------------
# Conversational copy (flow-spec wording, NOT the report E-* file taxonomy)
# ---------------------------------------------------------------------------

#: EC-1 — API failure / timeout, surfaced only after one silent retry. Copy never
#: exposes the server ``Reason``, an HTTP code, or a URL.
FETCH_ERROR_TEXT = "Couldn't fetch your brokerage details just now."

#: EC-7 — there is no document for brokerage; it is card-only by design.
NO_DOCUMENT_TEXT = (
    "There's no document for this one — your brokerage rates aren't a downloadable "
    "report. Here they are:"
)

#: EC-4 — a segment the user asked about isn't active on their plan; show what is
#: and offer a ticket for the rest.
OFF_PLAN_TEXT = (
    "Here's what's active on your plan. If you were expecting another segment, I can "
    "raise a ticket to get it checked."
)

#: EC-5 / EC-6 — a "what will X cost / how much brokerage" ask. Show the rate rows
#: and point to the contract note; never compute a rupee figure.
CALCULATION_POINTER_TEXT = (
    "These are your rate slabs. I don't compute the exact charge on a trade — the "
    "final brokerage for any trade is on that day's contract note."
)


def _retry_chip() -> Chip:
    return Chip(label="↺ Retry", action=ChipAction(kind=ChipActionKind.retry))


def _raise_ticket_chip() -> Chip:
    return Chip(label="🎫 Raise a ticket", action=ChipAction(kind=ChipActionKind.raise_ticket))


def _show_ledger_chip() -> Chip:
    # A prefilled prompt that re-enters the router and routes to the ledger flow.
    return Chip(
        label="Show my ledger",
        action=ChipAction(kind=ChipActionKind.send_text, payload={"text": "Show my ledger"}),
    )


# ---------------------------------------------------------------------------
# Response parsing + rendering (dynamic, verbatim)
# ---------------------------------------------------------------------------


def _parse_groups(payload: object) -> list[BrokerageGroup]:
    """Validate the ``Response`` array into segment groups. Iterates whatever the
    API returns; skips a malformed group rather than guessing its shape. Returns
    ``[]`` when the payload is not a non-empty array of groups (a fetch failure)."""
    if not isinstance(payload, list):
        return []
    groups: list[BrokerageGroup] = []
    for item in payload:
        try:
            groups.append(BrokerageGroup.model_validate(item))
        except ValidationError:
            continue
    return groups


def render_slab_card(groups: Sequence[BrokerageGroup]) -> DataCard:
    """Render the rate slabs as a dynamic data card: one section per group the API
    returned, one row per slab, with ``desc`` rendered VERBATIM into ``value``.

    No hardcoded segment names or row count, and no numeric parsing/computation of
    the rate text — the wire ``DataRow.value`` is the raw ``desc`` string."""
    return DataCard(
        groups=[
            DataGroup(
                title=group.title,
                list=[DataRow(label=row.title, value=row.desc) for row in group.list],
            )
            for group in groups
        ]
    )


def fetch_error_response() -> list[RenderBlock]:
    """EC-1 — the conversational failure bubble shown only after one silent retry.
    Never a toast; carries the retry/ticket recovery chips."""
    return [
        ErrorBubble(
            code=ErrorCode.E_TIMEOUT,
            text=FETCH_ERROR_TEXT,
            chips=[_retry_chip(), _raise_ticket_chip()],
        )
    ]


def no_document_response(groups: Sequence[BrokerageGroup]) -> list[RenderBlock]:
    """EC-7 — an "email/PDF me my brokerage" ask. There is no document path for
    brokerage; explain that and re-show the card."""
    return [Bubble(text=NO_DOCUMENT_TEXT), render_slab_card(groups)]


def off_plan_response(groups: Sequence[BrokerageGroup]) -> list[RenderBlock]:
    """EC-4 — a segment the user asked about isn't in their returned plan. Show the
    plan they do have and offer the recovery chips. Per the render-block sequence
    (proposal "Flow step / render-block sequence" step 3), off-plan and calculation
    asks share the ``[Show my ledger · 🎫 Raise a ticket]`` chip-row."""
    return [
        Bubble(text=OFF_PLAN_TEXT),
        render_slab_card(groups),
        ChipRow(chips=[_show_ledger_chip(), _raise_ticket_chip()]),
    ]


def calculation_pointer_response(groups: Sequence[BrokerageGroup]) -> list[RenderBlock]:
    """EC-5 / EC-6 — a "how much will this trade cost" ask. Show the rate rows and
    point to the contract note; never compute a rupee figure."""
    return [
        Bubble(text=CALCULATION_POINTER_TEXT),
        render_slab_card(groups),
        ChipRow(chips=[_show_ledger_chip(), _raise_ticket_chip()]),
    ]


# ---------------------------------------------------------------------------
# The single-shot flow
# ---------------------------------------------------------------------------


async def _fetch_slab(finx: FinXClient, client_id: str) -> list[BrokerageGroup] | None:
    """One brokerage fetch over the JWT ``go`` adapter. Returns the parsed segment
    groups, or ``None`` on any fetch failure the flow spec treats uniformly: a
    transport error/timeout, a non-Success envelope, or a missing/empty
    ``Response`` array. The typed transport exceptions live in finx-http-adapters
    and are integrated at runtime; the flow only needs the failure signal here."""
    try:
        env = await finx.go.get_brokerage_slab(BrokerageSlabRequest(ClientID=client_id))
    except Exception:
        return None
    if env.outcome is not Outcome.success:
        return None
    groups = _parse_groups(env.payload)
    return groups or None


class BrokerageFlow:
    """The single-shot Brokerage flow. Satisfies the frozen ``FlowSpec`` protocol
    (``intent``/``config``/``steps``); ``steps()`` is empty because there is no
    user-input step — the flow acts entirely on the intent."""

    intent: Intent = Intent.report_brokerage
    # No date window and no FY: brokerage is a single call on intent.
    config: FlowConfig = FlowConfig(intent=Intent.report_brokerage, window=DateWindow())

    def steps(self) -> Sequence[Step]:
        return ()

    async def handle(self, client_id: str, finx: FinXClient) -> list[RenderBlock]:
        """Fulfil the brokerage intent: one ``get-brokerage-slab`` call keyed by the
        session-gated ``ClientID``, one silent retry on failure, then either the
        dynamic data card or the conversational error bubble.

        ``client_id`` MUST come from the authenticated session (never proxied from
        user input) — it is bound to the session that owns the SSO JWT."""
        groups = await _fetch_slab(finx, client_id)
        if groups is None:
            # Exactly one silent auto-retry before surfacing anything to the user.
            groups = await _fetch_slab(finx, client_id)
        if groups is None:
            return fetch_error_response()
        return [render_slab_card(groups)]


#: The module-level attribute the engine's importlib discovery registry reads
#: (``FLOW_ATTR`` in app/contracts/flow.py). No registration import is added
#: anywhere — discovery loads this flow by module presence.
FLOW: BrokerageFlow = BrokerageFlow()
