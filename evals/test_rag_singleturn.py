"""Single-turn RAG `deepeval test run` target (eval-harness capability).

Diagnoses the `qa_chunks` retriever separately from generation. Each case is an
`LLMTestCase(input=<raw user query>, actual_output=<final generation>,
expected_output=<label, where available>, retrieval_context=[<qa_chunks>])`,
scored by the referenceless triad (AnswerRelevancy + Faithfulness +
ContextualRelevancy) plus ContextualPrecision/Recall where a label exists.

`input` is the RAW user query only — never the prompt template (spec §7.2).

Live target: `actual_output` + `retrieval_context` come from the assembled
retriever/generator via the `rag_runner` fixture (Wave 2). Skipped unless
`EVAL_LIVE=1`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from evals.metrics import rag_singleturn_metrics

pytestmark = pytest.mark.skipif(
    not os.getenv("EVAL_LIVE"),
    reason="Live single-turn RAG eval: set EVAL_LIVE=1 with an assembled retriever "
    "(rag_runner fixture) + judge key (Wave 2).",
)


@dataclass(frozen=True)
class RagSample:
    """One retriever-diagnosis case: a raw user query and an optional label.

    `expected_output` is provided only where the workbook labels an answer; its
    presence turns on ContextualPrecision/Recall for that case.
    """

    case_id: str
    query: str
    expected_output: str | None = None


#: Raw user queries (retriever diagnosis) — never the prompt template. Spans the
#: retrieval clusters incl. Hindi/Hinglish; labelled cases exercise precision/recall.
RAG_SAMPLES: list[RagSample] = [
    RagSample("A1", "How do I download my contract note?"),
    RagSample("A2", "Where can I see my brokerage charges?"),
    RagSample("A3", "मेरी P&L रिपोर्ट कहाँ मिलेगी?"),
    RagSample("A4", "kaise nikale tax report FinX me"),
    RagSample(
        "A5",
        "What is a CML and how do I get mine?",
        expected_output=(
            "The Client Master List (CML) is a record of the client's demat account "
            "and registration details; it can be requested and downloaded from within "
            "the Choice FinX app."
        ),
    ),
    RagSample(
        "B1",
        "How long does a fund withdrawal take to reflect?",
        expected_output=(
            "Withdrawal timelines are governed by the settlement cycle and bank "
            "processing; the app shows the expected credit date for each request."
        ),
    ),
]


@pytest.mark.parametrize("sample", RAG_SAMPLES, ids=[s.case_id for s in RAG_SAMPLES])
def test_rag_singleturn_triad(sample, rag_runner, judge):
    """Score one retriever case with the RAG triad (+ precision/recall if labelled)."""
    actual_output, retrieval_context = rag_runner(sample.query)
    test_case = LLMTestCase(
        input=sample.query,
        actual_output=actual_output,
        expected_output=sample.expected_output,
        retrieval_context=retrieval_context,
    )
    metrics = rag_singleturn_metrics(
        judge, with_labels=sample.expected_output is not None
    )
    assert_test(test_case=test_case, metrics=metrics)
