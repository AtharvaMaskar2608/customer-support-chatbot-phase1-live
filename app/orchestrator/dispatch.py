"""Deterministic dispatch for structured UI events (chip / calendar / stepper).

These turns BYPASS the LLM entirely and drive the flow-engine directly — no Claude
call. ``send_text`` / ``deep_link`` chips carry a prefilled prompt and are NOT
handled here; the orchestrator routes those to the agentic loop instead.
"""

from __future__ import annotations

from app.contracts.router import ExtractedParams, Intent, RaiseTicketInput
from app.contracts.wire import Bubble, ChipAction, ChipActionKind
from app.orchestrator.ports import Services, TurnResult
from app.orchestrator.state import ThreadState

CALL_SUPPORT_TEXT = "Connecting you to support — a teammate will take it from here."


def dispatch_event(action: ChipAction, state: ThreadState, services: Services) -> TurnResult:
    """Advance the conversation for a structured event without any Claude call."""
    result = TurnResult()
    kind = action.kind

    if kind is ChipActionKind.raise_ticket:
        # client_id bound from the SESSION, never from the action payload.
        data = RaiseTicketInput(
            client_id=state.user_id,
            query_type=str(action.payload.get("query_type", "general")),
            transcript_ref=str(action.payload.get("transcript_ref", state.thread_id)),
        )
        res = services.ticketing.raise_ticket(data)
        result.intent = Intent.raise_ticket
        from app.contracts.wire import Chip, TicketConfirmation

        result.blocks = [
            TicketConfirmation(
                ticket_id=res.ticket_id,
                message=f"Ticket {res.ticket_id} raised — status {res.status}.",
                chips=[Chip(label="📞 Call support", action=ChipAction(kind=ChipActionKind.call_support))],
            )
        ]
        result.tool_calls.append({"name": "raise_ticket", "input": {"client_id": state.user_id}, "is_error": False})
        return result

    if kind is ChipActionKind.call_support:
        result.intent = Intent.call_support
        result.blocks = [Bubble(text=CALL_SUPPORT_TEXT)]
        return result

    # Everything else (select_param / open_calendar / retry / email / show_more)
    # advances the active flow deterministically via the engine.
    flow_state = state.flow_state
    if flow_state is None:
        result.blocks = [Bubble(text="Let's pick that up fresh — what would you like?")]
        return result

    intent = flow_state.intent
    params = flow_state.collected or ExtractedParams()
    step = services.engine.step(flow_state, intent, params, action)
    state.flow_state = step.next_state
    result.intent = intent
    result.extracted_params = params
    result.blocks = list(step.blocks)
    return result
