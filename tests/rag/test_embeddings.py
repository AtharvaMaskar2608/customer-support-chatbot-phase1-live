"""Query embedding tests (proposal §What Changes — Query embedding, §5.1).

text-embedding-3-large @ 3072, dimension guard, and RagError normalization —
all with a fake client (no network).
"""

from __future__ import annotations

import pytest

from app.rag.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, QueryEmbedder
from app.rag.models import RagError


class _FakeEmbeddings:
    def __init__(self, vector, *, raises=None):
        self._vector = vector
        self._raises = raises
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self._raises:
            raise self._raises
        return type("Resp", (), {"data": [type("D", (), {"embedding": self._vector})()]})()


class _FakeOpenAI:
    def __init__(self, vector, *, raises=None):
        self.embeddings = _FakeEmbeddings(vector, raises=raises)


def test_embed_returns_vector_and_pins_model_and_dims():
    fake = _FakeOpenAI([0.1] * EMBEDDING_DIMENSIONS)
    embedder = QueryEmbedder(fake)
    vec = embedder.embed("how do I check my SIPs")
    assert len(vec) == EMBEDDING_DIMENSIONS
    # locked to the stored KB dimension + model
    assert fake.embeddings.kwargs["model"] == EMBEDDING_MODEL == "text-embedding-3-large"
    assert fake.embeddings.kwargs["dimensions"] == 3072
    assert fake.embeddings.kwargs["input"] == "how do I check my SIPs"


def test_wrong_dimension_is_rejected():
    # A -small / truncated vector (1536) against the 3072-dim KB must be rejected.
    embedder = QueryEmbedder(_FakeOpenAI([0.1] * 1536))
    with pytest.raises(RagError) as exc:
        embedder.embed("q")
    assert exc.value.stage == "embedding"


def test_client_failure_becomes_rag_error():
    embedder = QueryEmbedder(_FakeOpenAI(None, raises=RuntimeError("api down")))
    with pytest.raises(RagError) as exc:
        embedder.embed("q")
    assert exc.value.stage == "embedding"
    assert isinstance(exc.value.cause, RuntimeError)


def test_embedder_builds_without_api_key():
    # Constructible with no client/key (lazy) — only .embed() would need one.
    QueryEmbedder()
