"""Golden dataset assembly (eval-harness capability).

Combines the Phase-1 (A-E) and Phase-2 (F-M) `ConversationalGolden`s into one
`EvaluationDataset` and exposes category / severity / blocker accessors. All 17
workbook blocker cases are present; `assert_blocker_coverage()` proves the golden
set covers exactly the canonical `BLOCKER_CASE_IDS`.
"""

from __future__ import annotations

from deepeval.dataset import ConversationalGolden, EvaluationDataset

from evals.goldens._catalog import BLOCKER_CASE_IDS, CATEGORY_NAMES
from evals.goldens.phase1_kb import PHASE1_GOLDENS
from evals.goldens.phase2_api import PHASE2_GOLDENS

#: Every authored conversational golden (Phase 1 + Phase 2).
ALL_GOLDENS: list[ConversationalGolden] = [*PHASE1_GOLDENS, *PHASE2_GOLDENS]

#: The DeepEval dataset the simulator and test targets consume.
DATASET: EvaluationDataset = EvaluationDataset(goldens=list(ALL_GOLDENS))


def case_id(golden: ConversationalGolden) -> str:
    """The workbook case id (e.g. 'C3') stamped on a golden."""
    return golden.additional_metadata["case_id"]


def is_blocker(golden: ConversationalGolden) -> bool:
    """Whether a golden is a build-gating blocker case."""
    return bool(golden.additional_metadata["blocker"])


def blocker_goldens() -> list[ConversationalGolden]:
    """The subset of goldens whose failure holds the build."""
    return [g for g in ALL_GOLDENS if is_blocker(g)]


def goldens_by_category() -> dict[str, list[ConversationalGolden]]:
    """Goldens grouped by cluster letter (A-M)."""
    grouped: dict[str, list[ConversationalGolden]] = {k: [] for k in CATEGORY_NAMES}
    for g in ALL_GOLDENS:
        grouped[g.additional_metadata["category"]].append(g)
    return grouped


def assert_blocker_coverage() -> None:
    """Fail loudly if the authored blocker goldens do not match the canonical set."""
    authored = {case_id(g) for g in blocker_goldens()}
    missing = BLOCKER_CASE_IDS - authored
    extra = authored - BLOCKER_CASE_IDS
    if missing or extra:
        raise AssertionError(
            f"blocker coverage mismatch: missing={sorted(missing)} extra={sorted(extra)}"
        )


__all__ = [
    "ALL_GOLDENS",
    "DATASET",
    "PHASE1_GOLDENS",
    "PHASE2_GOLDENS",
    "BLOCKER_CASE_IDS",
    "case_id",
    "is_blocker",
    "blocker_goldens",
    "goldens_by_category",
    "assert_blocker_coverage",
]
