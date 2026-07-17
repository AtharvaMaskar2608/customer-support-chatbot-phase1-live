"""Writer behavior tests, written from the proposal's done condition.

Asserts the spec's promises, not the implementation's shape:
- enqueue() returns before the insert runs (response path never blocks on the DB);
- the worker inserts a TurnRecord with every §3.2 column populated;
- a forced insert error and a queue-full condition each log-and-drop without
  raising into the caller (identifiers only, never message PII);
- start()/stop() cleanly drain queued records and shut down.

Offline: a fake async connection double, never the live/prod DB.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from app.contracts.store import TURN_COLUMN_TO_FIELD
from app.store.writer import ConversationStoreWriter

from .conftest import FakeConnection, FakeFactory, make_record


# --- 1. Non-blocking: enqueue() returns before the insert runs -----------------


async def test_enqueue_is_nonblocking_insert_runs_off_request_path(fake_factory):
    """The core decoupling guarantee: after the synchronous enqueue() returns,
    the DB has NOT been touched — the insert only happens later on the worker."""
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()

    writer.enqueue(make_record())
    # No await between enqueue() and here, so the worker has had no chance to run:
    # the request path returned before any DB work occurred.
    assert fake_factory.conn.calls == []

    await writer.stop()  # drains — now the insert has run off the request path
    assert len(fake_factory.conn.calls) == 2  # threads upsert + turns insert


async def test_enqueue_returns_synchronously_without_awaiting():
    """enqueue is a plain (non-async) call — it cannot block the caller."""
    import inspect

    assert not inspect.iscoroutinefunction(ConversationStoreWriter.enqueue)


# --- 2. Full-column insert: every §3.2 column populated ------------------------


async def test_worker_persists_all_columns_and_commits(fake_factory):
    record = make_record()
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()
    writer.enqueue(record)
    await writer.stop()

    conn = fake_factory.conn
    assert len(conn.calls) == 2
    (thread_sql, thread_params), (turn_sql, turn_params) = conn.calls

    # Parent threads row upserted first (satisfies the FK, records user_id which
    # has no column on turns), idempotently.
    assert "INTO threads" in thread_sql
    assert "ON CONFLICT (thread_id) DO NOTHING" in thread_sql
    assert thread_params == (record.thread_id, record.user_id, record.model_version)

    # Turn row: targets the frozen 0001 table `turns`, one row per turn.
    assert "INTO turns" in turn_sql
    # Every mapped 0001 `turns` column appears in the INSERT column list.
    for column in TURN_COLUMN_TO_FIELD:
        assert column in turn_sql, f"missing column {column} in turns INSERT"

    # Re-enqueue idempotency guard (the 0002 unique index).
    assert "ON CONFLICT (thread_id, turn_number) DO NOTHING" in turn_sql

    # Params, in column order, every §3.2 field populated.
    assert turn_params[0] == record.turn_id
    assert turn_params[1] == record.thread_id
    assert turn_params[2] == record.turn_number
    assert turn_params[3] == record.user_message
    assert turn_params[4] == record.assistant_message
    assert turn_params[5] == record.intent.value  # detected_intent TEXT column
    assert turn_params[6].obj == record.extracted_params  # JSONB
    assert turn_params[7].obj == record.tool_calls  # JSONB name+args+result
    assert turn_params[8].obj == record.retrieval_context  # JSONB list[str]
    assert turn_params[9].obj == record.render_blocks  # JSONB
    assert turn_params[10] == record.latency_ms
    assert turn_params[11] == record.prompt_tokens
    assert turn_params[12] == record.completion_tokens
    assert turn_params[13] == record.model_version
    assert turn_params[14] == record.created_at

    assert conn.commits == 1  # single transaction per turn


async def test_optional_fields_none_do_not_break_insert(fake_factory):
    """A minimal record (only the required identity fields) still persists:
    optional JSONB defaults to [] and NULLs pass through; created_at unset falls
    back to now() at the SQL layer (COALESCE)."""
    record = make_record(
        user_message=None,
        assistant_message=None,
        intent=None,
        extracted_params=None,
        tool_calls=[],
        retrieval_context=[],
        render_blocks=[],
        latency_ms=None,
        prompt_tokens=None,
        completion_tokens=None,
        model_version=None,
        created_at=None,
    )
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()
    writer.enqueue(record)
    await writer.stop()

    _, (_, turn_params) = fake_factory.conn.calls
    assert turn_params[5] is None  # detected_intent
    assert turn_params[6] is None  # extracted_params -> NULL, not Jsonb(None)
    assert turn_params[7].obj == []  # tool_calls default
    assert turn_params[8].obj == []  # retrieval_context default
    assert turn_params[9].obj == []  # render_blocks default
    assert turn_params[14] is None  # created_at -> COALESCE(now()) at SQL layer
    assert fake_factory.conn.commits == 1


# --- 3. Forced insert error -> log-and-drop, worker survives -------------------


async def test_insert_error_logs_and_drops_without_raising(caplog):
    conn = FakeConnection(raise_on_execute=RuntimeError("db exploded"))
    factory = FakeFactory(conn)
    writer = ConversationStoreWriter(factory)
    await writer.start()

    rec1 = make_record(user_message="SECRET-PII-ONE")
    rec2 = make_record(user_message="SECRET-PII-TWO")
    with caplog.at_level(logging.WARNING, logger="app.store.writer"):
        writer.enqueue(rec1)
        writer.enqueue(rec2)
        await writer.stop()  # must NOT raise into the caller

    # Both records were processed -> the worker survived the first exception.
    assert writer.dropped_count == 2
    assert "store_write_dropped" in caplog.text
    # Identifiers logged, message PII never logged.
    assert rec1.thread_id in caplog.text and rec1.turn_id in caplog.text
    assert "SECRET-PII-ONE" not in caplog.text
    assert "SECRET-PII-TWO" not in caplog.text


# --- 4. Queue-full -> log-and-drop, enqueue never raises ----------------------


async def test_queue_full_logs_and_drops_without_raising(caplog):
    # maxsize=1 and no worker started -> the second enqueue finds a full queue.
    writer = ConversationStoreWriter(FakeFactory(FakeConnection()), queue_maxsize=1)
    a = make_record()
    b = make_record(user_message="DROP-ME-PII")

    with caplog.at_level(logging.WARNING, logger="app.store.writer"):
        writer.enqueue(a)  # fills the queue
        writer.enqueue(b)  # QueueFull -> drop, must not raise

    assert writer.dropped_count == 1
    assert writer._queue.qsize() == 1  # only A retained
    assert "store_write_dropped" in caplog.text
    assert "queue full" in caplog.text
    assert b.thread_id in caplog.text
    assert "DROP-ME-PII" not in caplog.text  # no message PII in the drop log


# --- 5. start()/stop() drain + clean shutdown ---------------------------------


async def test_stop_drains_all_queued_records(fake_factory):
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()
    records = [make_record(turn_number=i) for i in range(5)]
    for r in records:
        writer.enqueue(r)
    await writer.stop()

    # Every queued record drained: 5 turns * (threads upsert + turns insert).
    assert len(fake_factory.conn.calls) == 10
    assert fake_factory.conn.commits == 5
    assert writer.dropped_count == 0
    assert writer._worker_task is None  # cleanly released


async def test_stop_without_start_is_a_noop():
    writer = ConversationStoreWriter(FakeFactory(FakeConnection()))
    await writer.stop()  # must not raise
    assert writer._worker_task is None


async def test_start_is_idempotent(fake_factory):
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()
    task = writer._worker_task
    await writer.start()  # second start does not spawn a second worker
    assert writer._worker_task is task
    await writer.stop()


async def test_worker_continues_after_a_transient_failure(fake_factory):
    """A failing insert is dropped; the very next record still persists — the
    worker is not torn down by one exception."""
    conn = fake_factory.conn

    writer = ConversationStoreWriter(fake_factory)
    await writer.start()

    # First record: force the connection to raise; then clear the fault so the
    # second record succeeds.
    conn.raise_on_execute = RuntimeError("transient")
    writer.enqueue(make_record())
    await asyncio.sleep(0)  # let the worker attempt + drop the first
    while writer.dropped_count == 0:
        await asyncio.sleep(0)
    conn.raise_on_execute = None
    writer.enqueue(make_record())
    await writer.stop()

    assert writer.dropped_count == 1
    assert conn.commits == 1  # the second record committed


# --- 6. Worker holds its own connection (reused across turns; reconnect on error) --


async def test_worker_reuses_one_connection_across_turns(fake_factory):
    """The worker opens ITS OWN connection once and reuses it for every turn,
    closing it once at shutdown — not a connect/disconnect per turn."""
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()
    for i in range(4):
        writer.enqueue(make_record(turn_number=i))
    await writer.stop()

    assert fake_factory.call_count == 1  # one connection for all four turns
    assert fake_factory.conn.opened == 1
    assert fake_factory.conn.closed == 1  # released cleanly at stop
    assert fake_factory.conn.commits == 4


async def test_worker_reconnects_after_an_insert_error(fake_factory):
    """A failed insert discards the (possibly broken) connection; the next turn
    reconnects — so one bad turn does not poison the writer."""
    conn = fake_factory.conn
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()

    conn.raise_on_execute = RuntimeError("connection reset")
    writer.enqueue(make_record())
    while writer.dropped_count == 0:
        await asyncio.sleep(0)
    conn.raise_on_execute = None
    writer.enqueue(make_record())
    await writer.stop()

    assert writer.dropped_count == 1
    assert conn.commits == 1
    # Reconnected after the error: the factory was asked for a fresh connection
    # a second time (open on turn 1, discard on error, reopen on turn 2).
    assert fake_factory.call_count == 2
    assert conn.closed == 2  # broken conn closed after the error + clean close at stop


async def test_connection_factory_failure_is_contained(fake_conn):
    """If opening the connection itself raises, the record is dropped and the
    worker survives to serve the next record once the factory recovers."""
    factory = FakeFactory(fake_conn, open_error=RuntimeError("db down"))
    writer = ConversationStoreWriter(factory)
    await writer.start()

    writer.enqueue(make_record())
    while writer.dropped_count == 0:
        await asyncio.sleep(0)
    assert writer.dropped_count == 1  # open failed -> log-and-drop, worker alive

    factory.open_error = None  # DB comes back
    writer.enqueue(make_record())
    await writer.stop()
    assert fake_conn.commits == 1  # the worker recovered and persisted the next turn


async def test_stop_does_not_hang_if_worker_already_exited(fake_factory):
    """The no-hang guard: even if the worker task has exited with records still
    unfinished (task_done never called), stop() must not block forever on the
    drain."""
    writer = ConversationStoreWriter(fake_factory)
    await writer.start()

    # Simulate a dead worker: cancel its task and let it finish.
    writer._worker_task.cancel()
    try:
        await writer._worker_task
    except asyncio.CancelledError:
        pass
    # An unfinished item sits in the queue (queue.join() would block forever).
    writer.enqueue(make_record())

    # stop() must still return promptly rather than hang on queue.join().
    await asyncio.wait_for(writer.stop(), timeout=2.0)
    assert writer._worker_task is None
