"""T6: per-flow 15-minute selection/byte cache (proposal §Per-flow 15-min cache)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.contracts.flow import CacheConfig, selection_cache_key
from app.contracts.router import ExtractedParams, Intent

from app.engine.cache import SelectionCache

T0 = datetime(2026, 7, 17, 12, 0, 0)


def test_hit_within_ttl():
    cache = SelectionCache()
    key = selection_cache_key(Intent.report_pnl, ExtractedParams(fy="2024-2025"))
    cache.put(key, b"%PDF-bytes", now=T0)
    assert cache.get(key, now=T0 + timedelta(seconds=899)) == b"%PDF-bytes"


def test_miss_after_ttl_expiry():
    cache = SelectionCache()
    key = selection_cache_key(Intent.report_pnl, ExtractedParams(fy="2024-2025"))
    cache.put(key, b"%PDF-bytes", now=T0)
    # 900s is the frozen TTL — at/after it the entry is expired.
    assert CacheConfig().ttl_seconds == 900
    assert cache.get(key, now=T0 + timedelta(seconds=900)) is None
    # And it is evicted (a later in-TTL put/get is independent).
    assert cache.get(key, now=T0 + timedelta(seconds=1)) is None


def test_edit_changes_key_no_cross_contamination():
    cache = SelectionCache()
    key_a = selection_cache_key(Intent.report_pnl, ExtractedParams(fy="2024-2025"))
    key_b = selection_cache_key(Intent.report_pnl, ExtractedParams(fy="2023-2024"))
    assert key_a != key_b
    cache.put(key_a, b"report-A", now=T0)
    # A different selection (an edit) never reads the prior selection's bytes.
    assert cache.get(key_b, now=T0) is None
    assert cache.get(key_a, now=T0) == b"report-A"


def test_key_helper_matches_frozen():
    cache = SelectionCache()
    params = ExtractedParams(fy="2024-2025")
    assert cache.key(Intent.report_tax, params) == selection_cache_key(Intent.report_tax, params)
