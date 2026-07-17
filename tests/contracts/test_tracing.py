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
    inline_judge_allowed,
    new_thread_id,
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


def test_mask_redacts_email_embedded_in_string_value():
    # The registered-email leak lives INSIDE a confirmation string (not a PII key).
    data = {"confirmation": "PnL Report mail sent successfully to SANTOSH.HARSHA@GMAIL.COM"}
    masked = default_mask(data)
    assert "@" not in masked["confirmation"]
    assert "***" in masked["confirmation"]
    assert masked["confirmation"].startswith("PnL Report mail sent successfully to ")


def test_default_mask_is_the_configured_default():
    cfg = trace_manager.configure()
    assert cfg.mask is default_mask


def test_thread_stitching_and_production_judge_rule():
    # Per-turn traces are stitched by a shared thread_id (uuid4).
    tid = new_thread_id()
    assert isinstance(tid, str) and len(tid) == 36
    assert new_thread_id() != tid  # unique per session
    # No blocking judge metrics in production; allowed elsewhere.
    assert inline_judge_allowed("production") is False
    assert inline_judge_allowed("development") is True
    assert inline_judge_allowed("staging") is True


def test_typed_spans_carry_their_type_and_context():
    # llm span carries model + usage.
    with trace_manager.span(SpanType.llm, model="claude-sonnet-5") as span:
        span.set(prompt_tokens=10, completion_tokens=3)
    assert span.span_type is SpanType.llm
    assert span.attributes["model"] == "claude-sonnet-5"
    assert span.attributes["prompt_tokens"] == 10
    assert trace_manager.last_span.span_type is SpanType.llm

    # retriever span carries the canonical retrieval_context (list[str]).
    ctx = ["chunk one", "chunk two"]
    with trace_manager.span(SpanType.retriever, retrieval_context=ctx) as rspan:
        pass
    assert rspan.span_type is SpanType.retriever
    assert rspan.attributes["retrieval_context"] == ctx


def test_configure_records_deepeval_caveat():
    # The contract notes the DeepEval configure() single-param caveat.
    from app.contracts import tracing

    assert "openai_client" in tracing.TraceManager.__doc__
    assert "manually on the" in tracing.TraceManager.__doc__ or "llm" in tracing.TraceManager.configure.__doc__
