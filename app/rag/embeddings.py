"""Query embedding (rag-service capability, spec §5.1).

Embeds the user query with ``text-embedding-3-large`` at **3072 dimensions**,
locked to the stored KB dimension — ``-small`` (1536) and truncated vectors are
forbidden against the current ``qa_chunks`` KB. The OpenAI client is constructed
lazily so the embedder can be built (and unit-tested with a fake client) without
an API key or network. Embedding failures surface as ``RagError(stage="embedding")``
so the orchestrator maps them onto the shared error taxonomy.
"""

from __future__ import annotations

from typing import Any

from app.rag.models import RagError

#: The KB is embedded at the full 3072-dim size of text-embedding-3-large; query
#: vectors MUST match the stored dimension.
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072


class QueryEmbedder:
    """Embeds a query string into a 3072-dim vector for cosine search.

    The ``client`` (an OpenAI SDK client or any object exposing
    ``embeddings.create(...)``) is injectable and constructed lazily; tests pass a
    fake. ``dimensions`` is sent explicitly to pin the query vector to the stored
    KB dimension.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        model: str = EMBEDDING_MODEL,
        dimensions: int = EMBEDDING_DIMENSIONS,
    ) -> None:
        self._client = client
        self.model = model
        self.dimensions = dimensions

    def _openai(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def embed(self, query: str) -> list[float]:
        """Return the 3072-dim embedding of ``query``.

        Raises ``RagError(stage="embedding")`` on any client failure or if the
        provider returns a vector of the wrong dimension (a guard against wiring
        a ``-small``/truncated model against the 3072-dim KB).
        """
        try:
            response = self._openai().embeddings.create(
                model=self.model,
                input=query,
                dimensions=self.dimensions,
            )
            vector = list(response.data[0].embedding)
        except RagError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalize every failure to RagError
            raise RagError(
                "query embedding failed", stage="embedding", cause=exc
            ) from exc
        if len(vector) != self.dimensions:
            raise RagError(
                f"embedding dimension {len(vector)} != expected {self.dimensions}",
                stage="embedding",
            )
        return vector


__all__ = ["QueryEmbedder", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS"]
