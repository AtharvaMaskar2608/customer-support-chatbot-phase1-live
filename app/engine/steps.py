"""Step progression + stepper-edit semantics (proposal §Step progression / §8.4).

Resolves the next incomplete step from a flow's ordered steps, pre-filling steps
already satisfied by the router's ``ExtractedParams``; reopens a completed step
(clearing every downstream selection while preserving upstream ones); and builds
the editable stepper card. Pure and deterministic — no I/O.
"""

from __future__ import annotations

from app.contracts.flow import FlowState, Step, StepKind, StepState
from app.contracts.router import ExtractedParams
from app.contracts.flow import fy_long_to_short
from app.contracts.wire import Chip, StepperCard, StepperStep
from app.contracts.wire import StepState as WireStepState

from app.engine.ports import EngineContext, FlowDefinition

#: Steps that collect a selection from the user. ``generate`` is terminal (reaching
#: it triggers delivery); it is never "pre-filled" and never blocks progression.
COLLECTING_KINDS: frozenset[StepKind] = frozenset(
    {
        StepKind.segment,
        StepKind.date_range,
        StepKind.fy,
        StepKind.format,
        StepKind.delivery,
        StepKind.confirm,
    }
)

#: Which ``ExtractedParams`` field satisfies a given step kind. ``confirm`` has no
#: backing param — it is satisfied only by an explicit done mark on the state.
_KIND_TO_FIELD: dict[StepKind, str] = {
    StepKind.segment: "segment",
    StepKind.date_range: "date_range",
    StepKind.fy: "fy",
    StepKind.format: "report_format",
    StepKind.delivery: "delivery",
}


def param_for_kind(kind: StepKind) -> str | None:
    """The ``ExtractedParams`` field a step kind collects, or ``None``."""
    return _KIND_TO_FIELD.get(kind)


def _param_value(collected: ExtractedParams, kind: StepKind):
    field = param_for_kind(kind)
    return None if field is None else getattr(collected, field)


def label_for(collected: ExtractedParams, kind: StepKind) -> str | None:
    """A display label for a satisfied step's selection, derived from the value.
    The executor overrides this with the tapped chip's own label when it has one."""
    value = _param_value(collected, kind)
    if value is None:
        return None
    if kind is StepKind.fy:
        return fy_long_to_short(value)
    if kind is StepKind.date_range:
        parts = [d.isoformat() for d in (value.from_, value.to) if d is not None]
        return " – ".join(parts) if parts else None
    if kind is StepKind.format:
        # ReportFormat.pdf / .excel → "PDF" / "Excel".
        return "PDF" if value.value == "pdf" else value.value.title()
    # Segment / Delivery enums render their (underscored) value in title case.
    return value.value.replace("_", " ").title()


def _done_step_ids(state: FlowState) -> set[str]:
    return {s.id for s in state.steps if s.state is StepState.done}


def _is_done(step: Step, state: FlowState) -> bool:
    """A step is done if its backing param is already collected OR it carries an
    explicit done mark on the state (covers ``confirm``, which has no param)."""
    if _param_value(state.collected, step.kind) is not None:
        return True
    return step.id in _done_step_ids(state)


def next_step(state: FlowState, flow: FlowDefinition) -> Step | None:
    """The next incomplete collecting step, or ``None`` when the flow is ready to
    generate. Steps already satisfied by ``state.collected`` are skipped."""
    for step in flow.steps():
        if step.kind not in COLLECTING_KINDS:
            continue
        if not _is_done(step, state):
            return step
    return None


def materialize_steps(flow: FlowDefinition, state: FlowState) -> list[Step]:
    """Project the flow's ordered steps against the collected params: satisfied
    collecting steps become ``done`` (with a derived label), the first unsatisfied
    collecting step becomes ``active``, the rest ``pending``. ``generate`` steps are
    carried through as pending terminal markers."""
    active_assigned = False
    out: list[Step] = []
    for step in flow.steps():
        if step.kind not in COLLECTING_KINDS:
            out.append(step.model_copy(update={"state": StepState.pending}))
            continue
        if _is_done(step, state):
            out.append(
                step.model_copy(
                    update={
                        "state": StepState.done,
                        "selected_label": step.selected_label
                        or label_for(state.collected, step.kind),
                    }
                )
            )
        elif not active_assigned:
            out.append(step.model_copy(update={"state": StepState.active}))
            active_assigned = True
        else:
            out.append(step.model_copy(update={"state": StepState.pending}))
    return out


def reopen_step(state: FlowState, step_id: str) -> FlowState:
    """Reopen a completed step for editing: the target becomes ``active`` and every
    DOWNSTREAM step's selection is cleared (state → pending, label → None, backing
    param → None). Upstream steps are untouched. Nothing is re-fetched here — the
    cache key is invalidated so the next generation recomputes from the new
    selections (frozen ``selection_cache_key`` guarantees no cross-contamination)."""
    ids = [s.id for s in state.steps]
    if step_id not in ids:
        raise KeyError(f"unknown step id: {step_id!r}")
    idx = ids.index(step_id)

    new_steps: list[Step] = []
    cleared_fields: set[str] = set()
    for pos, step in enumerate(state.steps):
        if pos < idx:
            new_steps.append(step)
            continue
        if pos == idx:
            new_steps.append(step.model_copy(update={"state": StepState.active, "selected_label": None}))
        else:
            new_steps.append(step.model_copy(update={"state": StepState.pending, "selected_label": None}))
        field = param_for_kind(step.kind)
        if field is not None:
            cleared_fields.add(field)

    collected = state.collected.model_copy(update={f: None for f in cleared_fields})
    reopened = state.steps[idx]
    return state.model_copy(
        update={
            "steps": new_steps,
            "collected": collected,
            "current_step": reopened.kind,
            "cache_key": None,
        }
    )


def build_stepper_card(state: FlowState, flow: FlowDefinition, ctx: EngineContext) -> StepperCard:
    """The editable multi-step card. Done steps keep their selected label and stay
    tappable (the widget reopens them); the active step carries its choice chips."""
    rows: list[StepperStep] = []
    for step in state.steps:
        if step.kind not in COLLECTING_KINDS:
            continue
        chips: list[Chip] = flow.step_chips(step, ctx) if step.state is StepState.active else []
        rows.append(
            StepperStep(
                id=step.id,
                title=flow.step_title(step),
                state=WireStepState(step.state.value),
                selected_label=step.selected_label,
                chips=chips,
            )
        )
    return StepperCard(steps=rows)
