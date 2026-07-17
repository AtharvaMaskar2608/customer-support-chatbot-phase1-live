"""Shared fixtures for the tracing suite.

The DeepEval ``trace_manager`` is a process-wide singleton; tests that call the
real ``configure`` mutate it. Snapshot and restore its config attributes around
every test so the suite stays order-independent and offline.
"""

from __future__ import annotations

import pytest

from deepeval.tracing import trace_manager

_SNAPSHOT_ATTRS = (
    "environment",
    "sampling_rate",
    "custom_mask_fn",
    "confident_api_key",
    "anthropic_client",
    "openai_client",
)


@pytest.fixture(autouse=True)
def _restore_trace_manager():
    saved = {attr: getattr(trace_manager, attr, None) for attr in _SNAPSHOT_ATTRS}
    try:
        yield
    finally:
        for attr, value in saved.items():
            setattr(trace_manager, attr, value)
