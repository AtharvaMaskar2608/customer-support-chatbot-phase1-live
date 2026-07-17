"""Grounded generation + refusal/escalation (spec §5, workbook §7.4).

Claude answers ONLY from the retrieved chunks, cites the entries it used, and
obeys the refusal rules — the structured decision (``answer`` / ``citations`` /
``refused`` / ``refusal_reason``) is produced via **structured outputs**
(``output_config.format`` json_schema), never prompt-then-parse free-text JSON.
The result is assembled into the frozen ``RagAnswer``; ``retrieval_context`` is
attached from the real retrieved set (not model-produced). Behavioural mapping
onto the frozen ``RefusalReason``:

* D4 no useful match → ``no_relevant_context`` (orchestrator hands off to an agent)
* C-series investment advice → ``investment_advice``
* prompt-injection / out-of-scope → ``out_of_scope``
* B3 numeric-gap (a needed figure is not in context) → ``low_confidence``

LLM failures surface as ``RagError(stage="llm")``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contracts.router import Language
from app.contracts.tools import strict_input_schema
from app.llm.client import LLMClient
from app.rag.models import RagAnswer, RagError, RefusalReason, RetrievedChunk
from app.rag.prompts import build_system_prompt, build_user_message


class _GroundedOutput(BaseModel):
    """The model's structured output — the generation subset of ``RagAnswer``.

    ``retrieval_context`` is deliberately NOT here: it is our real retrieved set,
    attached by the generator, never produced by the model.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[str] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: RefusalReason | None = None


#: The structured-outputs schema (strict json_schema) derived from the frozen
#: generation model — same generator the frozen tool registry uses.
_OUTPUT_SCHEMA: dict[str, Any] = strict_input_schema(_GroundedOutput)

#: The ``output_config`` handed to the LLM client (passed through unchanged).
_OUTPUT_CONFIG: dict[str, Any] = {
    "format": {
        "type": "json_schema",
        "name": "rag_answer",
        "schema": _OUTPUT_SCHEMA,
    }
}


class Generator:
    """Grounded Claude generation over retrieved context only."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    def answer(
        self,
        query: str,
        context: list[RetrievedChunk],
        language: Language | None = None,
    ) -> RagAnswer:
        """Generate a grounded, citation-bearing answer over ``context`` only.

        No context → an immediate D4 refusal (no LLM call). Otherwise one grounded
        completion with structured output; citations are filtered to the retrieved
        chunk ids and the real retrieved text is attached as ``retrieval_context``.
        """
        retrieval_context = [chunk.text for chunk in context]

        if not context:
            return RagAnswer(
                answer="",
                citations=[],
                refused=True,
                refusal_reason=RefusalReason.no_relevant_context,
                retrieval_context=[],
            )

        try:
            response = self.llm.complete(
                messages=[{"role": "user", "content": build_user_message(query, context)}],
                system=build_system_prompt(language),
                output_config=_OUTPUT_CONFIG,
            )
        except RagError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalize LLM failures
            raise RagError("grounded generation failed", stage="llm", cause=exc) from exc

        out = self._parse(response.text)
        valid_ids = {chunk.chunk_id for chunk in context}
        citations = [] if out.refused else [c for c in out.citations if c in valid_ids]

        return RagAnswer(
            answer=out.answer,
            citations=citations,
            refused=out.refused,
            refusal_reason=out.refusal_reason,
            retrieval_context=retrieval_context,
        )

    @staticmethod
    def _parse(text: str) -> _GroundedOutput:
        """Deserialize the structured-output JSON into ``_GroundedOutput``.

        Structured outputs guarantee schema-valid JSON; a validation failure is
        therefore an LLM/contract failure, surfaced as ``RagError(stage="llm")``.
        """
        try:
            return _GroundedOutput.model_validate_json(text)
        except ValidationError as exc:
            raise RagError(
                "structured generation output was not schema-valid",
                stage="llm",
                cause=exc,
            ) from exc


__all__ = ["Generator"]
