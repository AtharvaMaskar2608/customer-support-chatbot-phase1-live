"""Phase-1 default remote-config values (remote-config capability, task 6.2).

Concrete defaults that validate against ``RemoteConfig``: limits (page size 10,
note threshold 50, message cap 10, follow-up cap 2), the per-surface chip sets and
greeting pool (verbatim from spec §8.4 / the entry mockups), ``whats_new``, the
product list, the per-flow calendar bounds (P&L / Ledger / Contract Note / Global
Detail / Tax), and the RAG tunables (25 / 60 / 5 / "none").
"""

from __future__ import annotations

from datetime import date

from app.config.schema import (
    GreetingPool,
    Limits,
    Product,
    RagTunables,
    RemoteConfig,
)
from app.contracts.flow import DateWindow
from app.contracts.router import Intent
from app.contracts.wire import Chip, ChipAction, ChipActionKind, WhatsNewItem


def _text_chip(label: str, text: str) -> Chip:
    return Chip(label=label, action=ChipAction(kind=ChipActionKind.send_text, payload={"text": text}))


# The four "Popular right now" support-entry chips (entry 1a).
_SUPPORT_CHIPS = [
    _text_chip("📊 Get my P&L", "Get my P&L"),
    _text_chip("📒 Show my ledger", "Show my ledger"),
    _text_chip("🧾 “How do I check my trade details?”", "How do I check my trade details?"),
    _text_chip("❓ What are my brokerage charges?", "What are my brokerage charges?"),
]

# The four Reports-entry fulfilment chips (entry 1b), by ticket volume.
_REPORTS_CHIPS = [
    _text_chip("📊 P&L Statement", "P&L Statement"),
    _text_chip("📒 Ledger", "Ledger"),
    _text_chip("📁 Holding Statement", "Holding Statement"),
    _text_chip("🧾 Tax Report", "Tax Report"),
]

_GREETING = GreetingPool(
    default="Hey {client_id} — what do you need?",
    morning="Good morning, {client_id} ☀️ What can I get for you?",
    market_hours="Hi {client_id} — markets are live. Need a report or a quick answer?",
    post_market="Hi {client_id} 👋 Markets are closed — I'm not.",
)

_WHATS_NEW = [
    WhatsNewItem(
        icon="⚡",
        title="11 reports, instant",
        body="P&L, Ledger, Holding, Tax Report + 7 more, delivered in chat as PDF or Excel.",
    ),
    WhatsNewItem(
        icon="🔓",
        title="No email verification",
        body="You're logged in, so your reports come straight to you.",
    ),
    WhatsNewItem(
        icon="🎫",
        title="Tickets",
        body="Raise a support ticket without leaving chat.",
    ),
]

_PRODUCTS = [
    Product(intent=Intent.report_pnl, label="P&L Statement"),
    Product(intent=Intent.report_ledger, label="Ledger"),
    Product(intent=Intent.report_mtf_ledger, label="MTF Ledger"),
    Product(intent=Intent.report_contract_notes, label="Contract Notes"),
    Product(intent=Intent.report_tax, label="Tax Report"),
    Product(intent=Intent.report_capital_gain, label="Capital Gain"),
    Product(intent=Intent.report_tax_pnl, label="Tax P&L"),
    Product(intent=Intent.report_cml, label="CML"),
    Product(intent=Intent.report_brokerage, label="Brokerage"),
    Product(intent=Intent.report_holding, label="Holding Statement"),
    Product(intent=Intent.report_global_detail, label="Global Detail"),
]

# Per-flow calendar bounds (differ by design; the engine reads these from config).
_CALENDAR_BOUNDS = {
    Intent.report_pnl: DateWindow(floor=date(2018, 1, 1), cap_relative_days=7, max_range_years=2),
    Intent.report_ledger: DateWindow(floor=date(2019, 1, 1), cap_relative_days=7),
    Intent.report_contract_notes: DateWindow(floor=date(2018, 1, 1), cap_relative_days=0),
    Intent.report_global_detail: DateWindow(floor=date(2018, 1, 1)),
    Intent.report_tax: DateWindow(fy_based=True),
}


#: The Phase-1 default remote config.
DEFAULT_CONFIG = RemoteConfig(
    limits=Limits(),
    support_chips=_SUPPORT_CHIPS,
    reports_chips=_REPORTS_CHIPS,
    reports_placeholder="or type: CML, Contract Note, Capital Gain, Global…",
    greeting=_GREETING,
    whats_new=_WHATS_NEW,
    products=_PRODUCTS,
    compliance_footer="Factual answers only — never investment advice.",
    calendar_bounds=_CALENDAR_BOUNDS,
    rag=RagTunables(),
)
