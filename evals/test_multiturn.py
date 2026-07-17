"""Multi-turn conversational `deepeval test run` target (eval-harness capability).

Runs the `ConversationSimulator` against each golden and scores the simulated
conversation with the metric set. Blocker-severity goldens HARD-gate the build:
any below-threshold metric raises through `assert_test`, so a single blocker
regression fails `deepeval test run` exactly as the workbook severity model holds
launch. Non-blocker goldens are scored for signal but do not gate.

Live target: needs the assembled app (a driver set via
`evals.simulator.set_default_driver`) and a judge key. Skipped unless
`EVAL_LIVE=1` — Wave 2 wires the live driver; Wave-1 CI only imports/collects it.
"""

from __future__ import annotations

import os

import pytest

from deepeval import assert_test, evaluate
from evals.goldens import ALL_GOLDENS, blocker_goldens, case_id, is_blocker
from evals.metrics import CHATBOT_ROLE, blocker_safety_metric, conversational_metrics

pytestmark = pytest.mark.skipif(
    not os.getenv("EVAL_LIVE"),
    reason="Live multi-turn eval: set EVAL_LIVE=1 with an assembled app driver + "
    "judge key (Wave 2). Structural authoring is covered offline by test_goldens.py.",
)

#: Blocker goldens gate the build; the rest are informational.
BLOCKER_GOLDENS = blocker_goldens()
NONBLOCKER_GOLDENS = [g for g in ALL_GOLDENS if not is_blocker(g)]


def _simulate(simulator, golden):
    """Simulate one golden into a `ConversationalTestCase`, stamped with Jini's
    role (RoleAdherence needs it) and the golden's workbook metadata."""
    cases = simulator.simulate(conversational_goldens=[golden], max_user_simulations=1)
    case = cases[0]
    case.chatbot_role = CHATBOT_ROLE
    case.additional_metadata = {
        **(getattr(case, "additional_metadata", None) or {}),
        **(golden.additional_metadata or {}),
    }
    return case


@pytest.mark.parametrize(
    "golden", BLOCKER_GOLDENS, ids=[case_id(g) for g in BLOCKER_GOLDENS]
)
def test_blocker_conversation_gates_build(golden, simulator, judge):
    """A blocker golden's failure fails the build.

    The conversational set plus the strict "never gives investment advice" safety
    GEval must all pass; `assert_test` raises on any below-threshold metric.
    """
    case = _simulate(simulator, golden)
    metrics = [*conversational_metrics(judge), blocker_safety_metric(judge)]
    assert_test(test_case=case, metrics=metrics)


@pytest.mark.parametrize(
    "golden", NONBLOCKER_GOLDENS, ids=[case_id(g) for g in NONBLOCKER_GOLDENS]
)
def test_nonblocker_conversation_scored(golden, simulator, judge):
    """Non-blocker goldens are scored for signal but do not gate the build.

    `evaluate` reports metric scores without raising, so only blocker goldens
    hold the line.
    """
    case = _simulate(simulator, golden)
    evaluate(test_cases=[case], metrics=conversational_metrics(judge))
