"""Engine ports — the seams between the flow-agnostic runtime and everything it
does not own: the byte-fetch primitive (adapters), the per-flow definition (the
six flow changes), and the session-scoped cache.

The frozen ``FlowSpec`` (``app.contracts.flow``) is the minimal discovery
contract — ``intent`` / ``config`` / ``steps()``. The engine needs more from a
flow at run time (how to title a step, which chips a step offers, how to generate
the report, delivery presentation). Because the six flow changes DEPEND ON the
engine, the engine defines that richer ``FlowDefinition`` contract here; each flow
module's module-level ``FLOW`` object satisfies it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from app.contracts.flow import FlowConfig, Step
from app.contracts.router import ExtractedParams, Intent, ReportFormat
from app.contracts.wire import Chip, SessionContext

# ---------------------------------------------------------------------------
# Byte-fetch + cache ports
# ---------------------------------------------------------------------------


class ByteFetcher(Protocol):
    """Server-side report-byte fetch primitive, owned by ``finx-http-adapters``
    (``fetch_report_bytes``). Async because the real implementation does an HTTP
    GET. Raises ``FinXFetchError`` on short/empty/wrong-magic bytes and
    ``FinXTimeoutError`` on network/timeout (see ``app.engine.faults``)."""

    async def __call__(self, url: str, *, expected_format: ReportFormat) -> bytes: ...


class CachePort(Protocol):
    """The session-scoped selection/byte cache surface the engine relies on."""

    def get(self, key: str, *, now: datetime) -> bytes | None: ...
    def put(self, key: str, data: bytes, *, now: datetime) -> None: ...


# ---------------------------------------------------------------------------
# Generation result — what a flow's adapter binding returns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportUrl:
    """Generation produced a report URL the engine must fetch server-side."""

    url: str
    report_format: ReportFormat = ReportFormat.pdf


@dataclass(frozen=True)
class ReportBytes:
    """Generation produced raw report bytes directly (contract-note download)."""

    data: bytes
    report_format: ReportFormat = ReportFormat.pdf


@dataclass(frozen=True)
class EmailResult:
    """Generation delivered by email. ``raw_email`` is the FinX-leaked registered
    email (uppercased) the engine masks before display. ``sent`` / ``failed`` split
    the requested formats so a partial dual-format failure surfaces EC-12."""

    raw_email: str
    sent: tuple[ReportFormat, ...] = (ReportFormat.pdf,)
    failed: tuple[ReportFormat, ...] = ()


@dataclass(frozen=True)
class NoData:
    """In-band business no-data result (HTTP 200 / Status:Fail) → E-NODATA."""

    reason: str | None = None


@dataclass(frozen=True)
class GenerationError:
    """Any other in-band non-success result → E-UNKNOWN."""

    reason: str | None = None


#: What a flow's ``generate`` binding returns.
GenerationResult = ReportUrl | ReportBytes | EmailResult | NoData | GenerationError


# ---------------------------------------------------------------------------
# Engine context (runtime deps; wraps the frozen, dep-free SessionContext)
# ---------------------------------------------------------------------------


@dataclass
class EngineContext:
    """Per-turn engine context. ``SessionContext`` is frozen and carries no runtime
    dependencies, so the engine wraps it with the injected byte-fetcher, the
    session cache, a clock, and the follow-up counters."""

    session: SessionContext
    byte_fetcher: ByteFetcher
    cache: CachePort
    now: datetime = field(default_factory=datetime.now)
    follow_up_count: int = 0
    follow_up_cap: int = 2


# ---------------------------------------------------------------------------
# Flow definition — the engine-facing contract each flow module satisfies
# ---------------------------------------------------------------------------


@runtime_checkable
class FlowDefinition(Protocol):
    """The full contract the engine drives. A superset of the frozen ``FlowSpec``:
    ``intent`` / ``config`` / ``steps()`` (discovery) plus the presentation and
    generation surface the engine needs. Each flow change's module-level ``FLOW``
    object implements this."""

    intent: Intent
    config: FlowConfig

    def steps(self) -> Sequence[Step]: ...

    # --- presentation ---
    def step_title(self, step: Step) -> str:
        """Human title for a stepper row."""

    def step_chips(self, step: Step, ctx: EngineContext) -> list[Chip]:
        """The selectable chips a step offers (segment / FY / format / delivery)."""

    def report_title(self, params: ExtractedParams) -> str:
        """A friendly, Client-ID-free base name for the delivered file (the engine
        applies the rename policy and the CML exception on top)."""

    # --- delivery declarations ---
    password_hint: str | None
    supports_email: bool
    default_format: ReportFormat

    # --- generation (adapter binding) ---
    async def generate(self, params: ExtractedParams, ctx: EngineContext) -> GenerationResult:
        """Invoke this flow's FinX adapter binding to produce the report."""
