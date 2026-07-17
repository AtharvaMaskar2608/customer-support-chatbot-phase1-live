"""The executor — ``advance`` (proposal §State-machine executor).

Given the current ``FlowState``, a ``FlowEvent``, and a ``FlowDefinition``, compute
the next ``FlowState`` and the ordered render blocks to emit. Deterministic; the only
I/O is invoking the flow's adapter binding at the generation step (through
``deliver``). Integrates step progression, the calendar/FY/follow-up guardrails, the
cache, delivery, and error mapping.
"""

from __future__ import annotations

from app.contracts.flow import FlowState, StepKind, StepState, selection_cache_key
from app.contracts.router import DateRange, ExtractedParams
from app.contracts.wire import ConversationState, ErrorBubble, RenderBlock

from app.engine.calendar import build_calendar, out_of_range_nudge, validate_range
from app.engine.delivery import deliver
from app.engine.errors import map_error
from app.engine.events import (
    Confirm,
    DateSelected,
    FollowUp,
    FlowEvent,
    ParamSelected,
    ReopenStep,
    Resend,
)
from app.engine.followups import enforce_followups
from app.engine.fy import resolve_fy
from app.engine.ports import EngineContext, FlowDefinition
from app.engine.results import EYearError, FlowStepResult
from app.engine.steps import (
    build_stepper_card,
    materialize_steps,
    next_step,
    param_for_kind,
    reopen_step,
)


async def advance(
    state: FlowState,
    event: FlowEvent,
    flow: FlowDefinition,
    *,
    ctx: EngineContext,
) -> FlowStepResult:
    """One deterministic turn: apply ``event`` and return the next state + blocks."""
    if isinstance(event, FollowUp):
        return _handle_followup(state, event, flow, ctx)
    if isinstance(event, Resend):
        return await _generate(state, flow, ctx, resend=True)
    if isinstance(event, ReopenStep):
        return _collecting_result(reopen_step(state, event.step_id), flow, ctx)
    if isinstance(event, Confirm):
        return await _handle_confirm(state, flow, ctx)
    if isinstance(event, DateSelected):
        return await _handle_date(state, event, flow, ctx)
    if isinstance(event, ParamSelected):
        return await _handle_param(state, event, flow, ctx)
    raise TypeError(f"unsupported event: {event!r}")


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _handle_followup(state, event: FollowUp, flow, ctx) -> FlowStepResult:
    # The router decided this turn is a follow-up; the engine enforces the cap.
    if not event.resolved:
        escalation = enforce_followups(ctx)
        if escalation is not None:
            return FlowStepResult(
                state=state,
                blocks=escalation.blocks,
                conversation_state=ConversationState.escalated,
                escalated=True,
            )
    return _collecting_result(state, flow, ctx)


async def _handle_confirm(state, flow, ctx) -> FlowStepResult:
    # Mark the active confirm step done (a confirm step has no backing param), then
    # progress. If the active step is not a confirm step, this is a no-op re-emit.
    active = _active_step(state)
    if active is None or active.kind is not StepKind.confirm:
        return _collecting_result(state, flow, ctx)
    steps = [
        s.model_copy(update={"state": StepState.done}) if s.id == active.id else s
        for s in state.steps
    ]
    state = state.model_copy(update={"steps": steps})
    return await _progress(state, flow, ctx)


async def _handle_param(state, event: ParamSelected, flow, ctx) -> FlowStepResult:
    collected = _merge(state.collected, event.update)
    state = state.model_copy(update={"collected": collected})
    state = state.model_copy(update={"steps": materialize_steps(flow, state)})
    if event.label:
        state = _apply_label(state, event.update, event.label)
    return await _progress(state, flow, ctx)


async def _handle_date(state, event: DateSelected, flow, ctx) -> FlowStepResult:
    today = ctx.now.date()
    if not validate_range(flow, event.from_, event.to, today=today):
        # Defensive reject (calendars already hard-disable these): nudge + re-emit.
        blocks = [out_of_range_nudge(flow, today), *_collecting_blocks(state, flow, ctx)]
        return FlowStepResult(state=state, blocks=blocks, conversation_state=ConversationState.collecting)
    collected = state.collected.model_copy(
        update={"date_range": DateRange(from_=event.from_, to=event.to)}
    )
    state = state.model_copy(update={"collected": collected})
    state = state.model_copy(update={"steps": materialize_steps(flow, state)})
    return await _progress(state, flow, ctx)


# ---------------------------------------------------------------------------
# Progression + generation
# ---------------------------------------------------------------------------


async def _progress(state, flow, ctx) -> FlowStepResult:
    if next_step(state, flow) is not None:
        return _collecting_result(state, flow, ctx)
    return await _generate(state, flow, ctx)


def _active_step(state: FlowState):
    return next((s for s in state.steps if s.state is StepState.active), None)


def _collecting_result(state, flow, ctx) -> FlowStepResult:
    active = _active_step(state)
    if active is not None:
        state = state.model_copy(update={"current_step": active.kind})
    return FlowStepResult(
        state=state,
        blocks=_collecting_blocks(state, flow, ctx),
        conversation_state=ConversationState.collecting,
    )


def _collecting_blocks(state, flow, ctx) -> list[RenderBlock]:
    blocks: list[RenderBlock] = [build_stepper_card(state, flow, ctx)]
    active = _active_step(state)
    if active is not None and active.kind is StepKind.date_range:
        blocks.append(build_calendar(flow, ctx.now.date()))
    return blocks


async def _generate(state, flow, ctx, *, resend: bool = False) -> FlowStepResult:
    params = state.collected

    # FY flows resolve the window BEFORE any adapter call — out-of-window ⇒ E-YEAR.
    if flow.config.window.fy_based:
        resolved = resolve_fy(params, ctx.now.date())
        if isinstance(resolved, EYearError):
            return FlowStepResult(
                state=state.model_copy(update={"current_step": StepKind.generate}),
                blocks=[map_error(resolved, flow, ctx=ctx, params=params)],
                conversation_state=ConversationState.error,
            )
        params = params.model_copy(update={"fy": resolved.fy_long})
        state = state.model_copy(update={"collected": params})

    blocks = await deliver(flow, params, ctx, resend=resend)
    is_error = any(isinstance(b, ErrorBubble) for b in blocks)
    state = state.model_copy(
        update={
            "current_step": StepKind.generate,
            "cache_key": selection_cache_key(flow.intent, params),
        }
    )
    return FlowStepResult(
        state=state,
        blocks=blocks,
        conversation_state=ConversationState.error if is_error else ConversationState.delivered,
    )


# ---------------------------------------------------------------------------
# Param merge helpers
# ---------------------------------------------------------------------------


def _merge(collected: ExtractedParams, update: ExtractedParams) -> ExtractedParams:
    changed = {name: getattr(update, name) for name in type(update).model_fields if getattr(update, name) is not None}
    return collected.model_copy(update=changed)


def _apply_label(state: FlowState, update: ExtractedParams, label: str) -> FlowState:
    changed_fields = {name for name in type(update).model_fields if getattr(update, name) is not None}
    steps = []
    for s in state.steps:
        field = param_for_kind(s.kind)
        if field in changed_fields and s.state is StepState.done:
            steps.append(s.model_copy(update={"selected_label": label}))
        else:
            steps.append(s)
    return state.model_copy(update={"steps": steps})
