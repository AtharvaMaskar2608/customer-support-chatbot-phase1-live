"""tracing-conventions spec tests.

Asserts the four-span taxonomy, the configure() setup contract (works without a
Confident AI key), and the mask hook (redacts names/emails/Client IDs/ledger
amounts).
"""

from __future__ import annotations

from app.contracts.tracing import (
    SpanType,
    TraceConfig,
    default_mask,
    trace_manager,
)


def test_span_taxonomy():
    assert {s.value for s in SpanType} == {"agent", "retriever", "llm", "tool"}
    assert len(list(SpanType)) == 4


def test_configure_accepts_documented_params_without_key():
    cfg = trace_manager.configure(
        openai_client=object(),
        environment="production",
        sampling_rate=0.5,
    )
    assert isinstance(cfg, TraceConfig)
    assert cfg.environment == "production"
    assert cfg.sampling_rate == 0.5
    # Functions without a Confident AI key (offline).
    assert cfg.confident_api_key is None
    assert cfg.export_enabled is False
    # With a key, export is enabled.
    cfg2 = trace_manager.configure(confident_api_key="ck-xyz")
    assert cfg2.export_enabled is True
    # sampling_rate defaults to 1.0.
    assert cfg2.sampling_rate == 1.0


def test_mask_redacts_pii():
    data = {
        "user_email": "san***.harsha@gmail.com",
        "FirstHolderName": "PRITAM NITIN WAVHAL",
        "client_id": "X008593",
        "Debit": 12345.67,
        "note": "process question",
        "nested": {"MobileNo": "9999999999", "safe": "ok"},
        "rows": [{"Credit": 100.0, "label": "fee"}],
    }
    masked = default_mask(data)
    # PII keys redacted.
    assert masked["user_email"] == "***"
    assert masked["FirstHolderName"] == "***"
    assert masked["client_id"] == "***"
    assert masked["Debit"] == "***"
    assert masked["nested"]["MobileNo"] == "***"
    assert masked["rows"][0]["Credit"] == "***"
    # Non-PII preserved.
    assert masked["note"] == "process question"
    assert masked["nested"]["safe"] == "ok"
    assert masked["rows"][0]["label"] == "fee"


def test_default_mask_is_the_configured_default():
    cfg = trace_manager.configure()
    assert cfg.mask is default_mask
