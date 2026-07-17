"""Tests for configure_tracing, the Anthropic A/B path probe, housekeeping, and
the production guard — written from proposal.md §6.2/§6.5 and the doneCondition.

Both auto-patch paths are exercised via a stubbed DeepEval ``configure`` (whose
signature includes/omits ``anthropic_client``). Offline: no Confident AI
connection, no real LLM call.
"""

from __future__ import annotations

import logging

import pytest

from deepeval.tracing import trace_manager

from app.tracing import (
    AUTO_PATCH,
    MANUAL_LLM_SPAN,
    LocalMetricsInProductionError,
    active_anthropic_path,
    assert_no_local_metrics,
    configure_tracing,
    maybe_clear_traces,
    mask_pii,
)


class _Recorder:
    """Records the kwargs the stubbed ``configure`` was called with."""

    def __init__(self):
        self.kwargs = None


def _stub_configure_with_anthropic(recorder):
    # Signature EXPOSES anthropic_client -> Path A.
    def configure(
        *,
        environment=None,
        sampling_rate=None,
        mask=None,
        confident_api_key=None,
        anthropic_client=None,
        openai_client=None,
    ):
        recorder.kwargs = {
            "environment": environment,
            "sampling_rate": sampling_rate,
            "mask": mask,
            "confident_api_key": confident_api_key,
            "anthropic_client": anthropic_client,
            "openai_client": openai_client,
        }

    return configure


def _stub_configure_openai_only(recorder):
    # Signature exposes ONLY openai_client -> Path B (the §6.2 caveat).
    def configure(
        *,
        environment=None,
        sampling_rate=None,
        mask=None,
        confident_api_key=None,
        openai_client=None,
    ):
        recorder.kwargs = {
            "environment": environment,
            "sampling_rate": sampling_rate,
            "mask": mask,
            "confident_api_key": confident_api_key,
            "openai_client": openai_client,
        }

    return configure


# --- Path A (auto-patch) -----------------------------------------------------


def test_path_a_forwards_pinned_anthropic_client(monkeypatch, caplog):
    rec = _Recorder()
    monkeypatch.setattr(trace_manager, "configure", _stub_configure_with_anthropic(rec))
    sentinel_client = object()

    with caplog.at_level(logging.INFO, logger="app.tracing"):
        configure_tracing("development", anthropic_client=sentinel_client)

    assert rec.kwargs["anthropic_client"] is sentinel_client
    assert rec.kwargs["mask"] is mask_pii
    assert rec.kwargs["environment"] == "development"
    assert active_anthropic_path() == AUTO_PATCH
    assert "path=A" in caplog.text


def test_path_a_selected_even_without_a_client(monkeypatch, caplog):
    rec = _Recorder()
    monkeypatch.setattr(trace_manager, "configure", _stub_configure_with_anthropic(rec))

    with caplog.at_level(logging.INFO, logger="app.tracing"):
        configure_tracing("production")

    # Path A is resolved from the installed signature; no client just means the
    # auto-patch hook has nothing pinned yet.
    assert active_anthropic_path() == AUTO_PATCH
    assert rec.kwargs["anthropic_client"] is None
    assert "path=A" in caplog.text


# --- Path B (manual llm-span, the §6.2 caveat) -------------------------------


def test_path_b_configures_without_client_and_logs_manual_path(monkeypatch, caplog):
    rec = _Recorder()
    monkeypatch.setattr(trace_manager, "configure", _stub_configure_openai_only(rec))
    # Even if a client is offered, Path B cannot forward it.
    with caplog.at_level(logging.INFO, logger="app.tracing"):
        configure_tracing("production", anthropic_client=object())

    assert "anthropic_client" not in rec.kwargs
    assert rec.kwargs["mask"] is mask_pii
    assert active_anthropic_path() == MANUAL_LLM_SPAN
    assert "path=B" in caplog.text


# --- Sampling defaults (§6.2) ------------------------------------------------


@pytest.mark.parametrize(
    "environment,expected_rate",
    [("development", 1.0), ("staging", 1.0), ("production", 0.1)],
)
def test_sampling_rate_defaults_by_environment(monkeypatch, environment, expected_rate):
    rec = _Recorder()
    monkeypatch.setattr(trace_manager, "configure", _stub_configure_with_anthropic(rec))
    configure_tracing(environment)
    assert rec.kwargs["sampling_rate"] == expected_rate


def test_explicit_sampling_rate_overrides_default(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(trace_manager, "configure", _stub_configure_with_anthropic(rec))
    configure_tracing("production", sampling_rate=0.5)
    assert rec.kwargs["sampling_rate"] == 0.5


def test_configure_is_idempotent(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(trace_manager, "configure", _stub_configure_with_anthropic(rec))
    configure_tracing("development")
    configure_tracing("development")  # second call must not raise
    assert rec.kwargs["environment"] == "development"


# --- Real (unstubbed) configure works offline --------------------------------


def test_configure_tracing_installs_mask_and_env_on_real_trace_manager():
    # No monkeypatch: exercise the live DeepEval configure offline (no key, no
    # client). Installed DeepEval exposes anthropic_client, so the live path=A.
    configure_tracing("production", sampling_rate=0.2)
    assert trace_manager.environment == "production"
    assert trace_manager.sampling_rate == 0.2
    assert trace_manager.custom_mask_fn is mask_pii
    assert trace_manager.confident_api_key is None  # offline
    assert active_anthropic_path() == AUTO_PATCH


# --- Housekeeping (§6.5) -----------------------------------------------------


def test_maybe_clear_traces_clears_when_offline(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(trace_manager, "confident_api_key", None)
    monkeypatch.setattr(trace_manager, "clear_traces", lambda: calls.__setitem__("n", calls["n"] + 1))
    maybe_clear_traces()
    assert calls["n"] == 1


def test_maybe_clear_traces_is_noop_when_exporting(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(trace_manager, "confident_api_key", "ck-xyz")
    monkeypatch.setattr(trace_manager, "clear_traces", lambda: calls.__setitem__("n", calls["n"] + 1))
    maybe_clear_traces()
    # Background worker drains exports; clearing would drop unexported traces.
    assert calls["n"] == 0


# --- Production guard (§6.5) -------------------------------------------------


def test_prod_guard_blocks_local_metrics_in_production():
    with pytest.raises(LocalMetricsInProductionError):
        assert_no_local_metrics("production", metrics=[object()])


def test_prod_guard_allows_empty_metrics_in_production():
    assert_no_local_metrics("production", metrics=None)
    assert_no_local_metrics("production", metrics=[])


@pytest.mark.parametrize("environment", ["development", "staging"])
def test_prod_guard_allows_local_metrics_outside_production(environment):
    assert_no_local_metrics(environment, metrics=[object()])
