"""Task 4 — deterministic language detection + §8.5 sticky-language (no LLM).

Drives ``_detect_language`` and ``_resolve_language`` directly. The sticky state
is asserted on the ``ConversationContext`` the router mutates in place.
"""

from __future__ import annotations

from app.contracts.router import ConversationContext, Language
from app.llm.router import _detect_language, _resolve_language


def _ctx(**overrides) -> ConversationContext:
    base = dict(
        user_id="X008593",
        session_id="s",
        access_token="t",
        platform="web",
        page="support",
    )
    base.update(overrides)
    return ConversationContext(**base)


def test_detect_language_devanagari_is_hindi():
    assert _detect_language("मुझे मेरा लेजर चाहिए") is Language.hindi


def test_detect_language_romanized_markers_is_hinglish():
    assert _detect_language("ledger chahiye") is Language.hinglish
    assert _detect_language("mujhe p&l report do") is Language.hinglish


def test_detect_language_plain_latin_is_english():
    assert _detect_language("get my ledger please") is Language.english


def test_common_english_words_do_not_trigger_hinglish():
    # Short tokens that collide with English ("do", "de", "ka", "ki") must NOT be
    # read as Hindi markers.
    assert _detect_language("how do i download my tax report") is Language.english
    assert _detect_language("what do the charges mean") is Language.english
    assert _detect_language("please do send my pnl") is Language.english


def test_english_locks_the_conversation():
    ctx = _ctx()
    assert _resolve_language("get my p&l", ctx, Language.english) is Language.english
    assert ctx.language_locked is True
    assert ctx.detected_language is Language.english


def test_locked_context_forces_english_over_hindi():
    ctx = _ctx(language_locked=True, detected_language=Language.english)
    # Even a Hindi utterance stays English once locked.
    assert _resolve_language("मुझे लेजर चाहिए", ctx, Language.hindi) is Language.english
    assert ctx.language_locked is True


def test_hindi_on_unlocked_context_does_not_lock():
    ctx = _ctx()
    assert _resolve_language("मुझे लेजर चाहिए", ctx, Language.hindi) is Language.hindi
    assert ctx.language_locked is False
    assert ctx.detected_language is Language.hindi


def test_hinglish_on_unlocked_context_does_not_lock():
    ctx = _ctx()
    assert _resolve_language("ledger chahiye", ctx, Language.hinglish) is Language.hinglish
    assert ctx.language_locked is False


def test_falls_back_to_heuristic_when_model_language_absent():
    ctx = _ctx()
    # No model language supplied → heuristic detects Hinglish, no lock.
    assert _resolve_language("ledger chahiye", ctx) is Language.hinglish
    assert ctx.language_locked is False
