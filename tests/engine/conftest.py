"""Shared engine-test fixtures: fake flow definitions, a scriptable fake
byte-fetcher, and context/state builders. Everything is offline — no network,
no LLM, no real adapters (the byte-fetch primitive is faked behind the frozen
seam per the proposal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Sequence

from app.contracts.flow import (
    DateWindow,
    FlowConfig,
    FlowState,
    Step,
    StepKind,
)
from app.contracts.router import ExtractedParams, Intent, ReportFormat
from app.contracts.wire import Chip, ChipAction, ChipActionKind, SessionContext

from app.engine.ports import EngineContext, GenerationResult, NoData
from app.engine.steps import materialize_steps


# ---------------------------------------------------------------------------
# Session + no-op cache
# ---------------------------------------------------------------------------


def make_session(**over) -> SessionContext:
    base = dict(
        user_id="X008593",
        session_id="sess-abc",
        access_token="jwt-xyz",
        platform="android",
        page="reports",
    )
    base.update(over)
    return SessionContext.from_url_params(
        userId=base["user_id"],
        sessionId=base["session_id"],
        accessToken=base["access_token"],
        platform=base["platform"],
        page=base["page"],
    )


class NoopCache:
    """A CachePort that never stores — used where caching is irrelevant."""

    def get(self, key: str, *, now: datetime):
        return None

    def put(self, key: str, data: bytes, *, now: datetime) -> None:
        return None


# ---------------------------------------------------------------------------
# Scriptable fake byte-fetcher (stands in for finx.adapters.fetch_report_bytes)
# ---------------------------------------------------------------------------


class FakeByteFetcher:
    """Returns / raises a scripted sequence, one entry per call. A bytes entry is
    returned; an Exception entry is raised (to simulate FinXFetchError/Timeout)."""

    def __init__(self, results: Sequence[bytes | Exception] = (b"%PDF-1.7 fake",)):
        self._results = list(results)
        self.calls = 0
        self.urls: list[str] = []
        self.formats: list[ReportFormat] = []

    async def __call__(self, url: str, *, expected_format: ReportFormat) -> bytes:
        self.calls += 1
        self.urls.append(url)
        self.formats.append(expected_format)
        result = self._results.pop(0) if self._results else b"%PDF-1.7 fake"
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# Fake flow definition
# ---------------------------------------------------------------------------


@dataclass
class FakeFlow:
    """A minimal FlowDefinition for tests. ``step_specs`` is an ordered list of
    ``(id, StepKind)``; ``generate_results`` is a queue of GenerationResult /
    Exception, one per ``generate`` call (drives the retry-once tests)."""

    intent: Intent = Intent.report_pnl
    window: DateWindow = field(default_factory=lambda: DateWindow(floor=date(2018, 1, 1), cap_relative_days=0, max_range_years=2))
    step_specs: list[tuple[str, StepKind]] = field(
        default_factory=lambda: [
            ("segment", StepKind.segment),
            ("dates", StepKind.date_range),
            ("delivery", StepKind.delivery),
            ("gen", StepKind.generate),
        ]
    )
    supports_email: bool = True
    password_hint: str | None = None
    default_format: ReportFormat = ReportFormat.pdf
    title: str = "P&L Statement"
    generate_results: list[GenerationResult | Exception] = field(default_factory=list)

    def __post_init__(self):
        self.config = FlowConfig(intent=self.intent, window=self.window)
        self.generate_calls = 0
        self.generate_params: list[ExtractedParams] = []

    def steps(self) -> Sequence[Step]:
        return [Step(id=i, kind=k) for (i, k) in self.step_specs]

    def step_title(self, step: Step) -> str:
        return step.id.replace("_", " ").title()

    def step_chips(self, step: Step, ctx: EngineContext) -> list[Chip]:
        return [Chip(label=f"{step.id}-choice", action=ChipAction(kind=ChipActionKind.select_param))]

    def report_title(self, params: ExtractedParams) -> str:
        return self.title

    async def generate(self, params: ExtractedParams, ctx: EngineContext) -> GenerationResult:
        self.generate_calls += 1
        self.generate_params.append(params)
        result = self.generate_results.pop(0) if self.generate_results else NoData()
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# Context + state builders
# ---------------------------------------------------------------------------


def make_ctx(
    *,
    cache=None,
    fetcher: FakeByteFetcher | None = None,
    now: datetime | None = None,
    follow_up_count: int = 0,
    follow_up_cap: int = 2,
    session: SessionContext | None = None,
    byte_validation=None,
) -> EngineContext:
    from app.contracts.flow import ByteValidation

    return EngineContext(
        session=session or make_session(),
        byte_fetcher=fetcher or FakeByteFetcher(),
        cache=cache or NoopCache(),
        now=now or datetime(2026, 7, 17, 12, 0, 0),
        follow_up_count=follow_up_count,
        follow_up_cap=follow_up_cap,
        byte_validation=byte_validation or ByteValidation(),
    )


def start_state(flow: FakeFlow, collected: ExtractedParams | None = None) -> FlowState:
    collected = collected or ExtractedParams()
    state = FlowState(intent=flow.intent, current_step=flow.steps()[0].kind, collected=collected)
    return state.model_copy(update={"steps": materialize_steps(flow, state)})
