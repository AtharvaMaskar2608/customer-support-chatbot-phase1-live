"""Shared RAG test fixtures.

Two worlds, per the proposal's test strategy:

* **Retrieval** runs against an ephemeral ``pgvector/pgvector:pg16`` container
  seeded from the committed ``fixtures/qa_chunks_seed.jsonl`` (real 3072-dim
  vectors captured from prod). This exercises the actual FTS + ``<=>`` + RRF SQL
  against real pgvector semantics. It **skips cleanly** when Docker or the image
  is unavailable (a pure-Python fake was rejected — it would not exercise the SQL
  that is the substance of this change).
* **Generation / refusal** uses ``FakeLLMClient`` (and, at the service layer,
  ``FakeRetriever``) — no DB, no network.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path

import psycopg
import pytest
from pgvector import Vector
from pgvector.psycopg import register_vector

from app.config.db import Database, make_engine
from app.llm.client import LLMResponse, Usage

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "qa_chunks_seed.jsonl"
PGVECTOR_IMAGE = "pgvector/pgvector:pg16"

# The seed table mirrors the columns the retriever reads from prod qa_chunks.
_SEED_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE qa_chunks (
    id           bigint PRIMARY KEY,
    topic        text,
    section      text,
    source_sheet text,
    source_row   integer,
    chunk        text NOT NULL,
    embedding    vector(3072)
);
"""

_INSERT = (
    "INSERT INTO qa_chunks (id, topic, section, source_sheet, source_row, chunk, embedding)"
    " VALUES (%(id)s, %(topic)s, %(section)s, %(source_sheet)s, %(source_row)s, %(chunk)s, %(embedding)s)"
)


def _run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )


def _docker_ready() -> bool:
    try:
        return _run("info", timeout=10).returncode == 0
    except Exception:
        return False


def _image_present() -> bool:
    try:
        return bool(_run("images", "-q", PGVECTOR_IMAGE, timeout=10).stdout.strip())
    except Exception:
        return False


def load_seed_rows() -> list[dict]:
    """Parse the committed JSONL fixture (embedding kept as a '[..]' string)."""
    with FIXTURE_PATH.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def seed_embedding(rows: list[dict], chunk_id: int) -> list[float]:
    """Return one fixture row's stored embedding as a Python list (for a
    FakeEmbedder that yields a real vector → deterministic vector ranking)."""
    for row in rows:
        if row["id"] == chunk_id:
            return json.loads(row["embedding"])
    raise KeyError(f"fixture has no row id={chunk_id}")


@pytest.fixture(scope="session")
def pgvector_db() -> Database:
    """Start a throwaway pgvector container, seed qa_chunks, yield a Database.

    Skips the whole retrieval suite when Docker or the image is unavailable.
    """
    if not _docker_ready():
        pytest.skip("Docker not available — retrieval SQL tests skipped")
    if not _image_present():
        pytest.skip(f"{PGVECTOR_IMAGE} image not present — retrieval SQL tests skipped")

    name = f"rag-pgvector-{uuid.uuid4().hex[:8]}"
    started = _run(
        "run", "-d", "--name", name,
        "-e", "POSTGRES_PASSWORD=jini",
        "-p", "127.0.0.1:0:5432",
        PGVECTOR_IMAGE,
    )
    if started.returncode != 0:
        pytest.skip(f"could not start pgvector container: {started.stderr.strip()}")

    try:
        port = _run("port", name, "5432").stdout.strip().split(":")[-1]
        dsn = f"postgresql://postgres:jini@127.0.0.1:{port}/postgres"

        deadline = time.time() + 45
        conn = None
        while time.time() < deadline:
            try:
                conn = psycopg.connect(dsn, connect_timeout=3)
                break
            except Exception:
                time.sleep(1)
        if conn is None:
            pytest.skip("pgvector container did not become ready in time")

        with conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(_SEED_DDL)
            register_vector(conn)
            rows = load_seed_rows()
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        _INSERT,
                        {
                            "id": row["id"],
                            "topic": row.get("topic"),
                            "section": row.get("section"),
                            "source_sheet": row.get("source_sheet"),
                            "source_row": row.get("source_row"),
                            "chunk": row["chunk"],
                            "embedding": Vector(json.loads(row["embedding"])),
                        },
                    )
        conn.close()

        yield make_engine(dsn)
    finally:
        _run("rm", "-f", name)


@pytest.fixture(scope="session")
def seed_rows() -> list[dict]:
    return load_seed_rows()


class FakeEmbedder:
    """Returns a fixed vector for any query — no network. When seeded with a real
    fixture-row embedding, vector ranking is deterministic (self-match at rank 1)."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector
        self.calls: list[str] = []

    def embed(self, query: str) -> list[float]:
        self.calls.append(query)
        return self._vector


class FakeLLMClient:
    """Replays a canned structured-output completion and records the request.

    ``raises`` forces a client error (to exercise RagError(stage='llm')).
    """

    def __init__(self, text: str = "", *, raises: Exception | None = None) -> None:
        self.text = text
        self.raises = raises
        self.requests: list[dict] = []

    def complete(self, **kwargs) -> LLMResponse:
        self.requests.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return LLMResponse(
            text=self.text,
            usage=Usage(prompt_tokens=1, completion_tokens=1),
            stop_reason="end_turn",
        )


class FakeRetriever:
    """Returns a canned RetrievedChunk list; records whether it was called."""

    def __init__(self, chunks) -> None:
        self.chunks = chunks
        self.calls: list[tuple] = []

    async def retrieve(self, query: str, k=None):
        self.calls.append((query, k))
        return list(self.chunks)
