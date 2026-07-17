"""Async, non-blocking conversation-store writer (conversation-store-writer).

After every bot response the orchestrator calls ``enqueue(TurnRecord)``, which
returns immediately. A single background worker (its own DB connection, from the
frozen ``db-config`` connection factory) drains the bounded queue and performs the
insert off the request path — the user-facing latency NEVER waits on this write.

Failure policy is **log + drop** (chosen in the proposal): on queue-full or insert
error, log the exception plus the dropped ``thread_id``/``turn_id`` (identifiers
only — never message PII) and emit a ``store_write_dropped`` metric, then drop the
record. A dropped row degrades the fine-tuning corpus, not the conversation; a
durable retry queue is explicitly deferred to Phase 2.

The persisted schema is the frozen contracts-foundation ``0001`` migration: a
``turns`` row per turn with a FK to its parent ``threads`` row. Because the
``TurnRecord``'s ``user_id`` has no column on ``turns`` (it lives on ``threads``)
and the FK requires the parent to exist, ``_insert_turn`` upserts the ``threads``
row before inserting the turn — in one transaction. ``0002`` adds the unique
``(thread_id, turn_number)`` index this writer's re-enqueue idempotency relies on.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from typing import Callable

from psycopg.types.json import Jsonb

from app.contracts.store import TurnRecord

logger = logging.getLogger("app.store.writer")

#: A callable returning an async context manager that yields a live DB connection
#: (psycopg 3 ``AsyncConnection``). This is exactly ``session_factory(engine)`` /
#: ``engine.connection`` from the frozen ``app/config/db.py`` — the ``db-config``
#: contract consumed from contracts-foundation.
ConnectionFactory = Callable[[], AbstractAsyncContextManager]

#: Upsert the parent thread so the turn's FK is satisfied and the record's
#: ``user_id`` (which has no column on ``turns``) is persisted. Idempotent per
#: thread; carries the identity fields only.
_UPSERT_THREAD_SQL = """
INSERT INTO threads (thread_id, user_id, model_version)
VALUES (%s::uuid, %s, %s)
ON CONFLICT (thread_id) DO NOTHING
"""

#: One fully-traced turn row. Column order is fixed and matches the frozen 0001
#: ``turns`` table (``detected_intent`` receives ``TurnRecord.intent``).
#: ``ON CONFLICT (thread_id, turn_number)`` (the 0002 unique index) makes a
#: re-enqueued turn a no-op. ``created_at`` falls back to ``now()`` when unset so
#: the NOT NULL default fires instead of an explicit NULL.
_INSERT_TURN_SQL = """
INSERT INTO turns (
    turn_id, thread_id, turn_number,
    user_message, assistant_message,
    detected_intent, extracted_params, tool_calls, retrieval_context, render_blocks,
    latency_ms, prompt_tokens, completion_tokens, model_version, created_at
)
VALUES (
    %s::uuid, %s::uuid, %s,
    %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, COALESCE(%s::timestamptz, now())
)
ON CONFLICT (thread_id, turn_number) DO NOTHING
"""


class ConversationStoreWriter:
    """Non-blocking persistence path for completed conversation turns.

    The orchestrator holds one instance for the app's lifetime, calls ``start()``
    in the FastAPI lifespan startup and ``stop()`` on shutdown, and calls the
    synchronous ``enqueue()`` after each bot response. All DB work happens on the
    single background worker task; the request path never awaits it.
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        queue_maxsize: int = 1000,
    ) -> None:
        self._connection_factory = connection_factory
        self._queue: asyncio.Queue[TurnRecord] = asyncio.Queue(maxsize=queue_maxsize)
        self._worker_task: asyncio.Task[None] | None = None
        #: ``store_write_dropped`` metric — records dropped by log-and-drop
        #: (queue-full + insert error). Read by tests and future instrumentation.
        self.dropped_count = 0

    async def start(self) -> None:
        """Spawn the background worker task (idempotent)."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker(), name="conversation-store-writer")

    async def stop(self) -> None:
        """Drain queued records, then cancel the worker and release it.

        Waits for every already-enqueued record to be processed (``queue.join()``)
        before cancelling, so a clean lifespan shutdown does not silently drop the
        tail of the queue.
        """
        if self._worker_task is None:
            return
        try:
            await self._queue.join()
        finally:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    def enqueue(self, record: TurnRecord) -> None:
        """Hand a completed turn to the writer. Non-blocking; NEVER raises into the
        caller. On a full queue: log + ``store_write_dropped`` metric + drop.

        This is the sole integration point with the orchestrator — it returns
        before the insert runs, so the response path never blocks on the DB.
        """
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self._drop(record, "queue full")

    async def _worker(self) -> None:
        """Drain the queue forever: insert each turn, log-and-drop on failure.

        A single failing insert must never kill the worker or surface to the
        caller — the loop catches everything, drops the record, and continues.
        Exactly one ``task_done()`` per pulled item keeps ``stop()``'s
        ``queue.join()`` accurate. Cancellation (from ``stop()``) propagates out.
        """
        while True:
            record = await self._queue.get()
            try:
                await self._insert_turn(record)
            except asyncio.CancelledError:
                self._queue.task_done()
                raise
            except Exception as exc:  # noqa: BLE001 — log-and-drop is the policy
                self._drop(record, "insert failed", exc)
            self._queue.task_done()

    async def _insert_turn(self, record: TurnRecord) -> None:
        """Persist one turn in a single transaction: upsert the parent thread
        (satisfies the FK, records ``user_id``), then insert the turn row with
        every §3.2 column populated."""
        async with self._connection_factory() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _UPSERT_THREAD_SQL,
                    (record.thread_id, record.user_id, record.model_version),
                )
                await cur.execute(_INSERT_TURN_SQL, self._turn_params(record))
            await conn.commit()

    @staticmethod
    def _turn_params(record: TurnRecord) -> tuple:
        """Positional params for ``_INSERT_TURN_SQL``, in column order. JSONB
        columns are wrapped in ``Jsonb``; ``intent`` becomes its enum ``value``
        for the ``detected_intent`` TEXT column."""
        return (
            record.turn_id,
            record.thread_id,
            record.turn_number,
            record.user_message,
            record.assistant_message,
            record.intent.value if record.intent is not None else None,
            Jsonb(record.extracted_params) if record.extracted_params is not None else None,
            Jsonb(record.tool_calls),
            Jsonb(record.retrieval_context),
            Jsonb(record.render_blocks),
            record.latency_ms,
            record.prompt_tokens,
            record.completion_tokens,
            record.model_version,
            record.created_at,
        )

    def _drop(self, record: TurnRecord, reason: str, exc: Exception | None = None) -> None:
        """Log-and-drop: identifiers only (never message PII) + metric bump."""
        self.dropped_count += 1
        logger.warning(
            "store_write_dropped: %s (thread_id=%s turn_id=%s turn_number=%s)",
            reason,
            record.thread_id,
            record.turn_id,
            record.turn_number,
            exc_info=exc,
        )
