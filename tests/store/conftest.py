"""Test doubles for the store writer — offline, never a live/prod DB.

An async fake mimicking the psycopg-3 ``AsyncConnection`` surface the writer uses
(``connection_factory()`` -> async CM -> ``conn.cursor()`` async CM -> ``await
cur.execute(sql, params)`` -> ``await conn.commit()``), recording every executed
statement so tests can assert what was persisted, and optionally raising to
exercise the log-and-drop failure path.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.contracts.router import Intent
from app.contracts.store import TurnRecord


class _FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self._conn = conn

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def execute(self, sql: str, params=None) -> None:
        self._conn.calls.append((sql, params))
        if self._conn.raise_on_execute is not None:
            raise self._conn.raise_on_execute


class _FakeConnCtx:
    def __init__(self, conn: "FakeConnection") -> None:
        self._conn = conn

    async def __aenter__(self) -> "FakeConnection":
        self._conn.opened += 1
        return self._conn

    async def __aexit__(self, *exc) -> bool:
        self._conn.closed += 1
        return False


class FakeConnection:
    """Records executed (sql, params) pairs and commits. Reused across
    ``_insert_turn`` calls so tests can assert on the accumulated calls."""

    def __init__(self, raise_on_execute: Exception | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0
        self.opened = 0
        self.closed = 0
        self.raise_on_execute = raise_on_execute

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    async def commit(self) -> None:
        self.commits += 1

    # --- assertion helpers ---
    @property
    def executed_sql(self) -> list[str]:
        return [sql for sql, _ in self.calls]

    def calls_touching(self, table: str) -> list[tuple[str, object]]:
        return [(sql, params) for sql, params in self.calls if f" {table} " in sql or f"INTO {table}" in sql]


class FakeFactory:
    """A connection factory mimicking ``session_factory(engine)`` /
    ``engine.connection``: a zero-arg callable returning an async context
    manager that yields the (single, recording) connection."""

    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def __call__(self) -> _FakeConnCtx:
        return _FakeConnCtx(self.conn)


@pytest.fixture
def fake_conn() -> FakeConnection:
    return FakeConnection()


@pytest.fixture
def fake_factory(fake_conn: FakeConnection) -> FakeFactory:
    return FakeFactory(fake_conn)


def make_record(**overrides) -> TurnRecord:
    """A fully-populated TurnRecord (every §3.2 field set) unless overridden."""
    base = dict(
        thread_id=str(uuid.uuid4()),
        turn_id=str(uuid.uuid4()),
        user_id="X008593",
        turn_number=1,
        user_message="show me my p&l for FY24",
        assistant_message="Here is your P&L statement.",
        intent=Intent.report_pnl,
        extracted_params={"fy": "2024-25"},
        tool_calls=[{"name": "GetGlobalPNLPDF", "args": {"fy": "2024-25"}, "result": {"ok": True}}],
        retrieval_context=["kb-chunk-1", "kb-chunk-2"],
        render_blocks=[{"type": "bubble", "text": "Here is your P&L statement."}],
        latency_ms=1234,
        prompt_tokens=321,
        completion_tokens=88,
        model_version="claude-fable-5",
        created_at=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return TurnRecord(**base)
