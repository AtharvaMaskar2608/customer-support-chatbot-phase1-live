"""Native tool-use agentic loop (Anthropic customer-support pattern, D15).

One free-text turn = forced ``route`` first, then an explicit ``while`` over
``stop_reason`` with the frozen tool registry. Structured decisions are ALWAYS
native ``tool_use`` blocks — never prompt-then-parse-JSON.

Loop contract (proposal §"Per-turn pipeline"):
  * ``tool_use`` → execute EVERY ``tool_use`` block server-side via the registry
    bindings, append the assistant content blocks plus a SINGLE user turn carrying
    ALL ``tool_result`` blocks (each matching its ``tool_use_id``; a failed
    execution returns ``is_error: true`` and is never dropped), then re-call.
    Splitting results across messages silently degrades parallel tool use, so they
    go in one message.
  * ``pause_turn`` → re-send the response and continue.
  * ``end_turn`` → break; the final text is the closing line.
  * ``refusal`` → the escalation chips.
  * Bounded: ≤3 tool iterations per turn, then escalate to ticket/call.

Fulfilment output comes from the TOOL RESULT (engine/rag/ticketing), never from
Claude prose. Tool inputs arrive API-validated (``strict: true``), so tool args are
not re-validated here — only the session-derived ``client_id`` binding is enforced.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.config.schema import Limits
from app.contracts.router import (
    ConversationContext,
    ExtractedParams,
    Intent,
    RaiseTicketInput,
    ROUTE_TOOL_CHOICE,
    ROUTE_TOOL_NAME,
    TicketStatusInput,
)
from app.contracts.tools import TOOLS, TOOLS_BY_NAME
from app.contracts.wire import Bubble, Chip, ChipAction, ChipActionKind, TicketConfirmation
from app.llm.client import LLMClient
from app.orchestrator.policy import (
    FOLLOW_UP_ESCALATION_TEXT,
    REFUSAL_TEXT,
    apply_sticky_language,
    escalation_blocks,
    follow_up_would_exceed,
)
from app.orchestrator.ports import Services, TurnResult
from app.orchestrator.state import ThreadState

#: The orchestrator's turn-level instruction. Routing/RAG prompts live in their own
#: changes; this only frames the turn (persona + compliance + tool discipline).
SYSTEM_PROMPT = (
    "You are Jini, Choice's post-login support assistant. Use the provided tools for "
    "every action — classify with `route`, then fulfil with the report/search/ticket "
    "tools. Deliver factual answers only; never give investment advice. Do not "
    "fabricate report contents — the tools produce them."
)

#: Fulfilment report tools → the Intent they fulfil.
REPORT_TOOL_TO_INTENT: dict[str, Intent] = {
    "get_pnl_report": Intent.report_pnl,
    "get_ledger_report": Intent.report_ledger,
    "get_contract_notes": Intent.report_contract_notes,
    "get_tax_report": Intent.report_tax,
    "get_cml": Intent.report_cml,
    "get_brokerage_slabs": Intent.report_brokerage,
}
REPORT_TOOL_NAMES = frozenset(REPORT_TOOL_TO_INTENT)

_ALL_TOOL_DEFS: list[dict[str, Any]] = [t.model_dump() for t in TOOLS]
_ROUTE_TOOL_DEFS: list[dict[str, Any]] = [TOOLS_BY_NAME[ROUTE_TOOL_NAME].model_dump()]

MAX_TOOL_ITERATIONS = 3
#: Safety bound so a pathological ``pause_turn`` stream cannot spin forever.
_SAFETY_CALLS = MAX_TOOL_ITERATIONS + 6


def _report_intent(name: str, tool_input: Mapping[str, Any]) -> Intent:
    if name == "get_ledger_report" and tool_input.get("mtf"):
        return Intent.report_mtf_ledger
    return REPORT_TOOL_TO_INTENT[name]


def _params_from_tool_input(tool_input: Mapping[str, Any]) -> ExtractedParams:
    allowed = {"fy", "date_range", "segment", "report_format", "delivery"}
    data = {k: v for k, v in tool_input.items() if k in allowed and v is not None}
    return ExtractedParams.model_validate(data)


def _summarize_blocks(blocks: Sequence[Any]) -> str:
    parts: list[str] = []
    for b in blocks:
        t = getattr(b, "type", "block")
        if t == "file_card":
            parts.append(f"file:{getattr(b, 'filename', '')}")
        elif t == "note_list_card":
            parts.append(f"notes:{len(getattr(b, 'rows', []))}")
        elif t == "error_bubble":
            parts.append(f"error:{getattr(getattr(b, 'code', None), 'value', b)}")
        else:
            parts.append(str(t))
    return ", ".join(parts)


def _call_support_chip() -> Chip:
    return Chip(label="📞 Call support", action=ChipAction(kind=ChipActionKind.call_support))


def _execute_tool(
    tu: Any,
    services: Services,
    state: ThreadState,
    context: ConversationContext,
    limits: Limits,
) -> tuple[str, list[Any], dict[str, Any], bool]:
    """Execute one ``tool_use`` block server-side. Returns (tool_result content,
    render blocks, meta, is_error). Never raises — a failure is surfaced as an
    ``is_error`` tool_result so the loop can continue."""
    name = tu.name
    tool_input: dict[str, Any] = dict(getattr(tu, "input", None) or {})
    meta: dict[str, Any] = {}
    try:
        if name == ROUTE_TOOL_NAME:
            rr = services.router.classify(tool_input, context)
            apply_sticky_language(state, rr.detected_language)
            meta["intent"] = rr.intent
            meta["extracted_params"] = rr.extracted_params
            if rr.escalate:
                meta["router_escalate"] = True
                meta["disambiguation_blocks"] = escalation_blocks(FOLLOW_UP_ESCALATION_TEXT)
            elif rr.follow_up_question is not None:
                if follow_up_would_exceed(state, limits):
                    meta["router_escalate"] = True
                    meta["disambiguation_blocks"] = escalation_blocks(FOLLOW_UP_ESCALATION_TEXT)
                else:
                    state.follow_up_count += 1
                    meta["disambiguation_blocks"] = [Bubble(text=rr.follow_up_question)]
            else:
                # A cleanly resolved routing turn ends the ambiguity streak.
                state.follow_up_count = 0
            return rr.model_dump_json(), [], meta, False

        if name in REPORT_TOOL_NAMES:
            intent = _report_intent(name, tool_input)
            params = _params_from_tool_input(tool_input)
            step = services.engine.step(state.flow_state, intent, params, None)
            state.flow_state = step.next_state
            meta["intent"] = intent
            meta["extracted_params"] = params
            return _summarize_blocks(step.blocks) or "delivered", list(step.blocks), meta, False

        if name == "search_kb":
            ans = services.rag.answer(tool_input.get("query", ""), state.history)
            meta["intent"] = Intent.rag_qa
            meta["retrieval_context"] = list(ans.retrieval_context)
            return ans.answer, [Bubble(text=ans.answer, compliance_footer=True)], meta, False

        if name == "raise_ticket":
            # client_id is bound from the SESSION, never from tool args (§2.6 / FLAG A).
            data = RaiseTicketInput(
                client_id=context.user_id,
                query_type=str(tool_input.get("query_type", "general")),
                transcript_ref=str(tool_input.get("transcript_ref", state.thread_id)),
            )
            res = services.ticketing.raise_ticket(data)
            meta["intent"] = Intent.raise_ticket
            block = TicketConfirmation(
                ticket_id=res.ticket_id,
                message=f"Ticket {res.ticket_id} raised — status {res.status}.",
                chips=[_call_support_chip()],
            )
            return f"ticket {res.ticket_id} {res.status}", [block], meta, False

        if name == "get_ticket_status":
            data = TicketStatusInput(ticket_ref=str(tool_input.get("ticket_ref", "")))
            res = services.ticketing.get_ticket_status(data)
            meta["intent"] = Intent.ticket_status
            return (
                f"{res.ticket_id} {res.status}",
                [Bubble(text=f"Ticket {res.ticket_id}: {res.status}.")],
                meta,
                False,
            )

        return f"unknown tool {name}", [], meta, True
    except Exception as exc:  # tool failure → is_error result, never dropped
        return f"tool {name} failed: {exc}", [], meta, True


def run_agentic_loop(
    *,
    llm: LLMClient,
    services: Services,
    text: str,
    state: ThreadState,
    context: ConversationContext,
    limits: Limits,
    max_tool_iterations: int = MAX_TOOL_ITERATIONS,
) -> TurnResult:
    """Drive one free-text turn through the native tool-use loop."""
    messages = list(state.messages)
    messages.append({"role": "user", "content": text})

    result = TurnResult()
    tool_iterations = 0
    total_calls = 0
    ended = False

    while total_calls < _SAFETY_CALLS:
        forced = total_calls == 0
        total_calls += 1
        resp = llm.complete(
            messages=messages,
            system=SYSTEM_PROMPT,
            tools=_ROUTE_TOOL_DEFS if forced else _ALL_TOOL_DEFS,
            tool_choice=ROUTE_TOOL_CHOICE if forced else {"type": "auto"},
        )
        stop = resp.stop_reason

        if stop == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue

        if stop == "refusal":
            result.blocks.extend(escalation_blocks(REFUSAL_TEXT))
            result.escalated = True
            ended = True
            break

        if stop == "tool_use":
            if tool_iterations >= max_tool_iterations:
                # Already ran the tool budget and the model wants MORE → escalate.
                result.blocks.extend(escalation_blocks(FOLLOW_UP_ESCALATION_TEXT))
                result.escalated = True
                ended = True
                break
            tool_iterations += 1
            messages.append({"role": "assistant", "content": resp.content})
            tool_results: list[dict[str, Any]] = []
            for tu in resp.tool_use:
                content, blocks, meta, is_error = _execute_tool(
                    tu, services, state, context, limits
                )
                result.blocks.extend(blocks)
                if meta.get("intent") is not None:
                    result.intent = meta["intent"]
                if meta.get("extracted_params") is not None:
                    result.extracted_params = meta["extracted_params"]
                if meta.get("retrieval_context"):
                    result.retrieval_context.extend(meta["retrieval_context"])
                if meta.get("disambiguation_blocks"):
                    result.blocks.extend(meta["disambiguation_blocks"])
                if meta.get("router_escalate"):
                    result.escalated = True
                result.tool_calls.append(
                    {"name": tu.name, "input": dict(getattr(tu, "input", None) or {}), "is_error": is_error}
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            continue

        # end_turn (or any other terminal, non-tool stop reason)
        result.assistant_text = resp.text
        ended = True
        break

    if not ended:
        result.blocks.extend(escalation_blocks(FOLLOW_UP_ESCALATION_TEXT))
        result.escalated = True

    result.tool_iterations = tool_iterations
    state.messages = messages
    return result
