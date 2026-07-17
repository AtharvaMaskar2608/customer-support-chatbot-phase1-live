"""conversation-store spec tests.

Asserts: the TurnRecord DTO fields correspond 1:1 with the 0001 `turns` columns;
retrieval_context uses the canonical list[str]; the 0001 migration creates
threads/turns with the FK + both indexes; and the forward-only runner discovers
0001 and is idempotent on re-run (dry-run parse — no live Postgres).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.contracts.rag import RetrievalContext
from app.contracts.store import TURN_COLUMN_TO_FIELD, TurnRecord
from app.store.migrations import runner

MIGRATIONS_DIR = Path(runner.__file__).parent
SQL_0001 = (MIGRATIONS_DIR / "0001_conversation_store.sql").read_text()


def _table_columns(sql: str, table: str) -> list[str]:
    """Extract column names from a CREATE TABLE block."""
    block = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", sql, re.DOTALL
    ).group(1)
    columns: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        token = line.split()[0]
        # Skip table-level constraints (none here, but be defensive).
        if token.upper() in {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK"}:
            continue
        columns.append(token)
    return columns


def test_turn_record_fields_map_one_to_one_to_columns():
    turns_columns = _table_columns(SQL_0001, "turns")
    # Every 0001 turns column has a TurnRecord field (via the documented map).
    assert set(turns_columns) == set(TURN_COLUMN_TO_FIELD.keys())
    record_fields = set(TurnRecord.model_fields.keys())
    for column, field in TURN_COLUMN_TO_FIELD.items():
        assert field in record_fields, (column, field)
    # TurnRecord adds only user_id (from threads) beyond the turns columns.
    mapped = set(TURN_COLUMN_TO_FIELD.values())
    assert record_fields - mapped == {"user_id"}


def test_retrieval_context_is_canonical_shape():
    assert TurnRecord.model_fields["retrieval_context"].annotation == RetrievalContext
    rec = TurnRecord(
        thread_id="t", turn_id="u", user_id="X1", turn_number=1,
        retrieval_context=["chunk a", "chunk b"],
    )
    assert rec.retrieval_context == ["chunk a", "chunk b"]


def test_0001_creates_tables_indexes_and_fk():
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in SQL_0001
    assert "CREATE TABLE IF NOT EXISTS threads" in SQL_0001
    assert "CREATE TABLE IF NOT EXISTS turns" in SQL_0001
    # FK turns.thread_id -> threads.thread_id.
    assert "REFERENCES threads(thread_id)" in SQL_0001
    # Both required indexes.
    assert "ON turns (thread_id)" in SQL_0001
    assert "ON turns (thread_id, turn_number)" in SQL_0001
    # turn_number present for the message cap.
    assert "turn_number" in _table_columns(SQL_0001, "turns")


def test_runner_discovers_and_is_idempotent():
    migrations = runner.discover_migrations(MIGRATIONS_DIR)
    names = [m.filename for m in migrations]
    assert "0001_conversation_store.sql" in names
    # Ascending numeric order.
    assert [m.number for m in migrations] == sorted(m.number for m in migrations)
    # Each migration parses (its SQL is readable and non-empty).
    for m in migrations:
        assert m.sql().strip()

    # Nothing applied yet → 0001 is pending.
    pending = runner.pending_migrations(set(), MIGRATIONS_DIR)
    assert "0001_conversation_store.sql" in [m.filename for m in pending]
    # After 0001 is applied → it is skipped (idempotent).
    pending_after = runner.pending_migrations({"0001_conversation_store.sql"}, MIGRATIONS_DIR)
    assert "0001_conversation_store.sql" not in [m.filename for m in pending_after]
