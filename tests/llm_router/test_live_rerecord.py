"""Manual/nightly live re-record (opt-in; deselected in CI).

Marked ``live`` — skipped by the conftest unless ``JINI_RUN_LIVE=1`` is set. When
run, it re-records the ``route`` tool_use input for every golden utterance against
the REAL pinned-model client, writes them to ``recordings/route_recordings.live.json``,
and asserts the golden ``RouterResult`` set still holds against the fresh
recordings. This is how the offline fixtures are refreshed; CI never runs it, so
``pytest tests/llm_router/`` makes no network call.
"""

from __future__ import annotations

import json

import pytest

from app.contracts.router import ConversationContext, RouterResult
from app.llm.router import Router
from tests.llm_router.fakes import FakeLLMClient


def _blank_ctx() -> ConversationContext:
    return ConversationContext(
        user_id="X008593", session_id="s", access_token="t", platform="web", page="support"
    )


def _ctx(overrides: dict) -> ConversationContext:
    base = dict(
        user_id="X008593", session_id="s", access_token="t", platform="web", page="support"
    )
    base.update(overrides or {})
    return ConversationContext(**base)


@pytest.mark.live
def test_live_rerecord_and_conform(goldens, recordings_dir):
    real = Router()  # real pinned-model LLMClient
    fresh: dict[str, dict] = {}
    for utterance in {c["utterance"] for c in goldens}:
        raw = real._classify(utterance, _blank_ctx())
        fresh[utterance] = raw.model_dump(mode="json", by_alias=True)

    (recordings_dir / "route_recordings.live.json").write_text(
        json.dumps(fresh, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    fake = FakeLLMClient(fresh)
    for case in goldens:
        result = Router(client=fake).route(case["utterance"], _ctx(case.get("ctx", {})))
        assert result == RouterResult.model_validate(case["expected"]), case["name"]
