"""Migration 0002 tests — the write-side idempotency guard applies on top of 0001.

Uses the real (read-only to this change) runner's pure discovery logic and a fake
sync DB-API connection, never a live DB (role lacks CREATEDB; suite is offline).
"""

from __future__ import annotations

from app.store.migrations.runner import (
    apply_migrations,
    discover_migrations,
    pending_migrations,
)

_0001 = "0001_conversation_store.sql"
_0002 = "0002_turns_idempotency_guard.sql"


def test_0002_discovered_in_order_after_0001():
    names = [m.filename for m in discover_migrations()]
    assert names[:2] == [_0001, _0002]  # ascending numeric order, 0002 after 0001


def test_0002_is_pending_once_0001_is_applied():
    pending = [m.filename for m in pending_migrations({_0001})]
    assert pending == [_0002]  # 0001 skipped, 0002 still to apply


def test_0002_is_the_unique_thread_turn_guard():
    sql = next(m.sql() for m in discover_migrations() if m.filename == _0002)
    assert "CREATE UNIQUE INDEX" in sql
    assert "turns (thread_id, turn_number)" in sql
    # Forward-only, additive: never edits/drops the frozen 0001 schema.
    upper = sql.upper()
    assert "DROP " not in upper
    assert "ALTER " not in upper


class _FakeSyncCursor:
    def __init__(self, store: dict) -> None:
        self._store = store

    def __enter__(self) -> "_FakeSyncCursor":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def execute(self, sql: str, params=None) -> None:
        self._store["executed"].append(sql)
        low = sql.strip().lower()
        if low.startswith("select filename from schema_migrations"):
            self._store["last_select"] = list(self._store["applied"])
        elif low.startswith("insert into schema_migrations"):
            self._store["applied"].add(params[0])

    def fetchall(self):
        return [(f,) for f in self._store["last_select"]]


class _FakeSyncConn:
    """Minimal DB-API double: enough for the runner's cursor/execute/commit path."""

    def __init__(self) -> None:
        self.store = {"applied": set(), "executed": [], "last_select": []}

    def cursor(self) -> _FakeSyncCursor:
        return _FakeSyncCursor(self.store)

    def commit(self) -> None:
        pass


def test_apply_runs_0001_then_0002_and_is_idempotent():
    conn = _FakeSyncConn()

    ran = apply_migrations(conn)
    assert ran == [_0001, _0002]  # both applied, 0001 before 0002

    # The 0002 unique-index DDL actually reached the DB in this run.
    assert any("CREATE UNIQUE INDEX" in sql for sql in conn.store["executed"])

    # Re-running applies nothing (both recorded in schema_migrations).
    assert apply_migrations(conn) == []
