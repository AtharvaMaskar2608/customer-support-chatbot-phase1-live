"""Shared async DB access (design D4/D14).

The single access point for both the ``qa_chunks`` read path (RAG) and the
conversation-store write path. Uses ``psycopg`` (psycopg 3) — one driver serving
both the async request/RAG path and the sync writer-thread / migration-runner
path — with the ``pgvector`` adapter registered on each connection.

Constructing the engine opens NO connection; connections are opened lazily inside
the ``connection()`` context manager.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from pgvector.psycopg import register_vector_async


def _normalize_dsn(dsn: str) -> str:
    """Strip a SQLAlchemy-style ``+psycopg`` driver suffix so libpq accepts the
    DSN (the .env DATABASE_URL uses ``postgresql+psycopg://``)."""
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


class Database:
    """Async engine holder: keeps the DSN and opens pgvector-registered
    connections on demand. No connection is opened at construction."""

    def __init__(self, dsn: str) -> None:
        self.dsn = _normalize_dsn(dsn)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[psycopg.AsyncConnection]:
        """Open an async connection with the pgvector adapter registered."""
        conn = await psycopg.AsyncConnection.connect(self.dsn)
        try:
            await register_vector_async(conn)
            yield conn
        finally:
            await conn.close()


def make_engine(dsn: str) -> Database:
    """Construct the shared async engine (no live connection opened)."""
    return Database(dsn)


def session_factory(engine: Database):
    """The single session factory: returns the connection context-manager
    callable used by both the RAG read path and the store write path."""
    return engine.connection
