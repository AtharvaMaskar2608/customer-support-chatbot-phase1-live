"""remote-config spec tests.

Asserts the RemoteConfig schema shape, the whats_new ≤3 rule, the Phase-1
defaults (limits, per-surface chips, greeting pool, per-flow calendar bounds,
RAG tunables), and that RAG tunables / Freshdesk mapping stay server-only.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.config.defaults import DEFAULT_CONFIG
from app.config.schema import Limits, RagTunables, RemoteConfig, WhatsNewItem
from app.contracts.router import Intent


def test_schema():
    # RemoteConfig carries the expected sections; no Freshdesk field mapping.
    fields = set(RemoteConfig.model_fields.keys())
    assert {
        "limits",
        "support_chips",
        "reports_chips",
        "reports_placeholder",
        "greeting",
        "whats_new",
        "products",
        "compliance_footer",
        "calendar_bounds",
        "rag",
    } <= fields
    assert not any("freshdesk" in f for f in fields)

    # whats_new accepts at most three items.
    with pytest.raises(ValidationError):
        RemoteConfig(
            limits=Limits(),
            support_chips=[],
            reports_chips=[],
            reports_placeholder="",
            greeting=DEFAULT_CONFIG.greeting,
            whats_new=[WhatsNewItem(icon="a", title="b", body="c")] * 4,
            products=[],
            compliance_footer="",
            calendar_bounds={},
            rag=RagTunables(),
        )


def test_defaults_validate():
    cfg = DEFAULT_CONFIG
    # Limits defaults.
    assert cfg.limits.contract_note_page_size == 10
    assert cfg.limits.note_narrow_threshold == 50
    assert cfg.limits.message_cap == 10
    assert cfg.limits.follow_up_cap == 2

    # Per-surface chips: four each.
    assert len(cfg.support_chips) == 4
    assert len(cfg.reports_chips) == 4
    assert cfg.reports_placeholder.startswith("or type:")

    # Greeting pool carries the {client_id} placeholder in each variant.
    for variant in (cfg.greeting.default, cfg.greeting.morning, cfg.greeting.market_hours, cfg.greeting.post_market):
        assert "{client_id}" in variant

    # whats_new ≤ 3.
    assert len(cfg.whats_new) <= 3

    # RAG tunables defaults (25 / 60 / 5 / "none"), server-only.
    assert cfg.rag.rag_candidate_k == 25
    assert cfg.rag.rrf_k == 60
    assert cfg.rag.rag_context_k == 5
    assert cfg.rag.reranker == "none"

    # Compliance footer text.
    assert cfg.compliance_footer == "Factual answers only — never investment advice."


def test_per_flow_calendar_bounds_differ():
    bounds = DEFAULT_CONFIG.calendar_bounds
    # P&L: floor 2018, cap today+7, max 2-year (730d) range.
    pnl = bounds[Intent.report_pnl]
    assert pnl.floor == date(2018, 1, 1)
    assert pnl.cap_relative_days == 7
    assert pnl.max_range_days == 730
    # Contract-note cap is today (0), ledger floor is 2019 — per-flow difference.
    assert bounds[Intent.report_contract_notes].cap_relative_days == 0
    assert bounds[Intent.report_contract_notes].floor == date(2018, 1, 1)
    assert bounds[Intent.report_ledger].floor == date(2019, 1, 1)
    # Tax is FY-based, not a date range.
    assert bounds[Intent.report_tax].fy_based is True
