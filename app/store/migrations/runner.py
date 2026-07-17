"""Forward-only numbered SQL migration runner (conversation-store, design D5).

Applies ``NNNN_description.sql`` files in ascending numeric order, tracking applied
files in a ``schema_migrations`` table, and applies only not-yet-applied files.
No Alembic (there are no ORM models to introspect). This change owns ``0001`` and
the runner; the conversation-store-writer change owns ``0002+`` (the runner is
read-only to it).

Run with ``python -m app.store.migrations.runner`` against a live database. The
discovery and pending-set logic are pure so they can be exercised offline (dry-run
parse) without a live Postgres.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MIGRATIONS_DIR = Path(__file__).parent
_MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")

_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class Migration:
    number: int
    filename: str
    path: Path

    def sql(self) -> str:
        return self.path.read_text()


def discover_migrations(migrations_dir: Path | None = None) -> list[Migration]:
    """All ``NNNN_*.sql`` files in ascending numeric order."""
    directory = migrations_dir or _MIGRATIONS_DIR
    found: list[Migration] = []
    for path in directory.glob("*.sql"):
        match = _MIGRATION_RE.match(path.name)
        if match:
            found.append(Migration(number=int(match.group(1)), filename=path.name, path=path))
    return sorted(found, key=lambda m: m.number)


def pending_migrations(
    applied: set[str], migrations_dir: Path | None = None
) -> list[Migration]:
    """The not-yet-applied migrations, in numeric order (pure — no DB)."""
    return [m for m in discover_migrations(migrations_dir) if m.filename not in applied]


def _fetch_applied(conn: Any) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(_SCHEMA_MIGRATIONS_DDL)
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def apply_migrations(conn: Any, migrations_dir: Path | None = None) -> list[str]:
    """Apply every pending migration in numeric order against a live DB-API
    connection, recording each in ``schema_migrations``. Idempotent: re-running
    after ``0001`` applies only later un-applied files. Returns the filenames
    applied this run."""
    applied = _fetch_applied(conn)
    ran: list[str] = []
    for migration in pending_migrations(applied, migrations_dir):
        with conn.cursor() as cur:
            cur.execute(migration.sql())
            cur.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)",
                (migration.filename,),
            )
        conn.commit()
        ran.append(migration.filename)
    return ran


if __name__ == "__main__":  # pragma: no cover
    import os

    import psycopg

    from app.config.db import _normalize_dsn

    dsn = _normalize_dsn(os.environ["DATABASE_URL"])
    with psycopg.connect(dsn) as connection:
        applied = apply_migrations(connection)
        print("applied:", applied or "(none pending)")
