"""Shared async DB access tests (design D4/D14, task 6.3).

Constructs the engine + session factory WITHOUT opening a live connection, and
checks the SQLAlchemy-style +psycopg suffix is normalized for libpq.
"""

from __future__ import annotations

from app.config.db import Database, make_engine, session_factory


def test_engine_factory():
    engine = make_engine("postgresql+psycopg://u:p@localhost:5433/db")
    assert isinstance(engine, Database)
    # +psycopg driver suffix normalized for libpq; no connection opened.
    assert engine.dsn == "postgresql://u:p@localhost:5433/db"

    # The single session factory returns the connection context-manager callable.
    factory = session_factory(engine)
    assert callable(factory)
    assert factory == engine.connection  # the connection context-manager, bound
