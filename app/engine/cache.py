"""Per-flow 15-minute selection/byte cache (proposal §Per-flow 15-min cache; 02 §2.5).

Session-scoped, keyed by the frozen ``selection_cache_key(intent, params)`` so a
change to any selection yields a new key and cached bytes are never reused after an
edit (no cross-contamination). TTL is the frozen ``CacheConfig.ttl_seconds`` (900s).
``resend`` bypass is enforced by the delivery path (it skips the lookup); the cache
itself is a plain get/put store. One ``SelectionCache`` per session/``EngineContext``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.contracts.flow import CacheConfig, selection_cache_key
from app.contracts.router import ExtractedParams, Intent

# Re-exported so callers key the cache through one place.
key_for = selection_cache_key


@dataclass
class _Entry:
    data: bytes
    stored_at: datetime


class SelectionCache:
    """A TTL byte cache scoped to a single session. Not thread-safe by design —
    one session is one logical actor."""

    def __init__(self, ttl_seconds: int | None = None):
        self._ttl = timedelta(seconds=ttl_seconds if ttl_seconds is not None else CacheConfig().ttl_seconds)
        self._store: dict[str, _Entry] = {}

    def get(self, key: str, *, now: datetime) -> bytes | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if now - entry.stored_at >= self._ttl:
            del self._store[key]  # expired — evict
            return None
        return entry.data

    def put(self, key: str, data: bytes, *, now: datetime) -> None:
        self._store[key] = _Entry(data=data, stored_at=now)

    def key(self, intent: Intent, params: ExtractedParams) -> str:
        """Convenience: the frozen selection key for an (intent, params) pair."""
        return selection_cache_key(intent, params)
