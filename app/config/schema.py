"""Remote-config schema (remote-config capability).

The runtime-tunable config: limits, per-surface chip sets, the time-aware
greeting pool, ``whats_new`` (≤3), the product list, the compliance footer, the
per-flow calendar bounds (server-only), and the RAG tunables (server-only). The
Freshdesk field mapping is NOT here — it is ticketing-owned config
(``app/ticketing/freshdesk.yaml``).

The client-relevant slice (chips, greeting, client-facing limits, ``whats_new``)
is delivered to the widget inside the first ``/api/chat`` response (``ConfigSlice``);
server-only config (calendar-bound math, RAG tunables) is never sent (D10).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.contracts.flow import DateWindow
from app.contracts.router import Intent
from app.contracts.wire import Chip, WhatsNewItem


class Limits(BaseModel):
    """Tunable runtime limits (change without a redeploy)."""

    model_config = ConfigDict(extra="forbid")

    contract_note_page_size: int = 10
    note_narrow_threshold: int = 50
    message_cap: int = 10
    follow_up_cap: int = 2


class GreetingPool(BaseModel):
    """Time-aware greeting templates. Each carries the ``{client_id}`` placeholder
    (Phase-1 greets by Client ID). Time ranges are ``HH:MM`` strings."""

    model_config = ConfigDict(extra="forbid")

    default: str
    morning: str
    market_hours: str
    post_market: str
    morning_range: tuple[str, str] = ("06:00", "09:00")
    market_hours_range: tuple[str, str] = ("09:15", "15:30")
    post_market_range: tuple[str, str] = ("15:30", "23:00")


class RagTunables(BaseModel):
    """RAG retrieval tunables — SERVER-ONLY (never sent to the widget)."""

    model_config = ConfigDict(extra="forbid")

    rag_candidate_k: int = 25
    rrf_k: int = 60
    rag_context_k: int = 5
    reranker: str = "none"


class Product(BaseModel):
    """A report type mapped to its customer-facing label."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    label: str


class RemoteConfig(BaseModel):
    """The complete runtime-tunable config schema (frozen surface)."""

    model_config = ConfigDict(extra="forbid")

    limits: Limits
    support_chips: list[Chip]  # the four "Popular right now" starter chips
    reports_chips: list[Chip]  # the four fulfilment chips
    reports_placeholder: str  # rotating long-tail placeholder
    greeting: GreetingPool
    whats_new: list[WhatsNewItem]  # at most three
    whats_new_cache_hours: int = 24  # 24-hour cache for What's New
    whats_new_red_dot: bool = True  # per-client-code red-dot badge (entries never auto-popup)
    products: list[Product]
    compliance_footer: str
    calendar_bounds: dict[Intent, DateWindow]  # per-flow; SERVER-ONLY
    rag: RagTunables  # SERVER-ONLY

    @field_validator("whats_new")
    @classmethod
    def _at_most_three_whats_new(cls, value: list[WhatsNewItem]) -> list[WhatsNewItem]:
        if len(value) > 3:
            raise ValueError("whats_new accepts at most three items")
        return value
