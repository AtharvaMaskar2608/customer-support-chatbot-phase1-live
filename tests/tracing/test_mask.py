"""Tests for ``mask_pii`` — written from proposal.md's concrete redaction list.

Every PII class the proposal enumerates must be redacted in nested inputs and
outputs; non-PII must pass through unchanged. Tokens are asserted verbatim
against the proposal.
"""

from __future__ import annotations

from app.tracing import mask_pii


# --- Key-based redaction (names + the frozen PII_KEYS) -----------------------


def test_masks_pii_by_structured_field_key():
    data = {
        "user_email": "santosh.harsha@gmail.com",
        "FirstHolderName": "PRITAM NITIN WAVHAL",
        "client_name": "Pritam",
        "full_name": "Pritam Nitin Wavhal",
        "client_id": "X008593",
        "Debit": 12345.67,
        "MobileNo": "9999999999",
        "access_token": "eyJhbGci...",
    }
    masked = mask_pii(data)
    assert masked["user_email"] == "***"
    assert masked["FirstHolderName"] == "***"
    assert masked["client_name"] == "***"
    assert masked["full_name"] == "***"
    assert masked["client_id"] == "***"
    assert masked["Debit"] == "***"
    assert masked["MobileNo"] == "***"
    assert masked["access_token"] == "***"


def test_leaves_non_pii_intact():
    data = {
        "note": "process question",
        "turn_number": 3,
        "model_version": "v1",
        "nested": {"safe": "ok"},
        "rows": [{"label": "fee"}],
        "iso_timestamp": "1900-01-01T00:00:00.000",
    }
    masked = mask_pii(data)
    assert masked["note"] == "process question"
    assert masked["turn_number"] == 3
    assert masked["model_version"] == "v1"
    assert masked["nested"]["safe"] == "ok"
    assert masked["rows"][0]["label"] == "fee"
    # A millisecond ISO timestamp is not a currency amount — left alone.
    assert masked["iso_timestamp"] == "1900-01-01T00:00:00.000"


# --- Value-based redaction (PII embedded inside string values) ---------------


def test_redacts_email_embedded_in_string_value():
    # Registered-email leak inside a confirmation string (not under a PII key).
    data = {"confirmation": "PnL Report mail sent successfully to SANTOSH.HARSHA@GMAIL.COM"}
    masked = mask_pii(data)
    assert "@" not in masked["confirmation"]
    assert masked["confirmation"] == "PnL Report mail sent successfully to [EMAIL_REDACTED]"


def test_redacts_already_masked_email_form():
    # The app's own masked email form still contains a live domain — redact it.
    assert mask_pii("san***.harsha@gmail.com") == "[EMAIL_REDACTED]"


def test_redacts_client_id_as_bare_value():
    # A FinX Client ID appearing as a bare string value under a non-PII key.
    assert mask_pii({"reference": "X008593"}) == {"reference": "[CLIENT_ID]"}
    assert mask_pii("A12345") == "[CLIENT_ID]"


def test_redacts_pan_embedded_in_string():
    # PAN is the PDF password — must never trace, even inside free text.
    assert mask_pii("Your PAN is ABCDE1234F for the report") == "Your PAN is [PAN] for the report"


def test_redacts_currency_amounts_in_strings():
    assert mask_pii("Closing balance ₹12,345.67 today") == "Closing balance [AMOUNT] today"
    assert mask_pii("Net 12345.67 debited") == "Net [AMOUNT] debited"


def test_redacts_phone_numbers_in_strings():
    assert mask_pii("Call 9876543210 now") == "Call [PHONE] now"
    assert mask_pii("Reach +919876543210 anytime") == "Reach [PHONE] anytime"


# --- Recursion + structure ---------------------------------------------------


def test_recurses_nested_dicts_lists_and_strings():
    data = {
        "outer": {
            "MobileNo": "9999999999",
            "messages": [
                "sent to a.b@x.io",
                {"PAN": "ABCDE1234F", "free": "ref X008593"},
            ],
        }
    }
    masked = mask_pii(data)
    # key-based inside nested dict
    assert masked["outer"]["MobileNo"] == "***"
    # value-based inside a list of strings
    assert masked["outer"]["messages"][0] == "sent to [EMAIL_REDACTED]"
    # key-based inside a dict nested in a list
    assert masked["outer"]["messages"][1]["PAN"] == "***"
    # The Client-ID value pattern is anchored (`^...$`) per the proposal, so a
    # Client ID *embedded* in a sentence is not value-redacted here (it would be
    # key-redacted under any PII key). This locks in the spec's anchored choice.
    assert masked["outer"]["messages"][1]["free"] == "ref X008593"


def test_preserves_tuple_shape():
    assert mask_pii(("santosh.harsha@gmail.com", "safe")) == ("[EMAIL_REDACTED]", "safe")


def test_is_idempotent():
    data = {"email": "a@b.com", "msg": "mail to x@y.com about ₹1,000.00"}
    once = mask_pii(data)
    assert mask_pii(once) == once


def test_conforms_to_frozen_mask_signature():
    # mask_pii is a valid MaskFn: Callable[[Any], Any] returning same-shape data.
    from app.contracts.tracing import MaskFn  # noqa: F401

    assert callable(mask_pii)
    assert mask_pii(42) == 42
    assert mask_pii(None) is None
