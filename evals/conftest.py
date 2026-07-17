"""Pytest fixtures for the eval harness (dataset, judge, simulator, RAG runner).

Split by lifetime: the offline structural tests (`test_goldens.py`,
`test_callback.py`) request none of these fixtures and never touch a judge or the
app; the live `deepeval test run` targets (`test_multiturn.py`,
`test_rag_singleturn.py`) are skipped unless `EVAL_LIVE=1`, so their fixtures only
resolve in Wave 2.

`@deepeval.log_hyperparameters` runs at *decoration* time and touches the
test-run manager, so it is registered only under `EVAL_LIVE` — the offline gate
never triggers test-run machinery.
"""

from __future__ import annotations

import os

import pytest

from evals.goldens import ALL_GOLDENS, DATASET
from evals.judge import JUDGE_MODEL, build_judge
from evals.metrics import load_thresholds


@pytest.fixture(scope="session")
def judge():
    """The eval judge / simulated-user model (claude-opus-4-8 by default)."""
    return build_judge()


@pytest.fixture(scope="session")
def goldens():
    """Every authored conversational golden (Phase 1 + Phase 2)."""
    return ALL_GOLDENS


@pytest.fixture(scope="session")
def dataset():
    """The DeepEval `EvaluationDataset` the simulator and targets consume."""
    return DATASET


@pytest.fixture(scope="session")
def simulator(judge):
    """The `ConversationSimulator` wired to the Jini callback + judge model.

    Requires a driver configured via `evals.simulator.set_default_driver` (Wave 2
    binds the live `HttpJiniDriver` against the assembled app).
    """
    from evals.simulator import build_simulator

    return build_simulator(judge)


@pytest.fixture(scope="session")
def rag_runner():
    """Callable `query -> (actual_output, retrieval_context)` for the RAG triad.

    The retriever/generator seam for single-turn RAG cases. Wave-1 leaves it
    unbound; Wave 2 overrides this fixture to hit the assembled retriever. It
    refuses to run until then, so the guard is explicit rather than a silent
    empty result.
    """

    def _unwired(_query: str):
        raise RuntimeError(
            "No RAG runner wired. Wave-1 authors the single-turn RAG targets and "
            "skips them offline; Wave 2 overrides the `rag_runner` fixture to drive "
            "the assembled retriever/generator."
        )

    return _unwired


def _register_hyperparameters() -> None:
    """Record judge model + proposed thresholds on the DeepEval test run.

    Guarded behind EVAL_LIVE: the decorator executes immediately and writes to the
    test-run manager, which must not happen during the offline structural gate.
    """
    import deepeval

    @deepeval.log_hyperparameters
    def hyperparameters() -> dict[str, str]:
        params: dict[str, str] = {
            "judge_model": os.getenv("JINI_JUDGE_PROVIDER", JUDGE_MODEL),
            "system_under_test": "claude-sonnet-5",
        }
        for section, values in load_thresholds().items():
            if isinstance(values, dict):
                for key, value in values.items():
                    params[f"{section}.{key}"] = str(value)
            else:
                params[section] = str(values)
        return params


if os.getenv("EVAL_LIVE"):
    _register_hyperparameters()
