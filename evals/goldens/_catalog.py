"""Shared golden catalog helpers (eval-harness capability).

`make_golden` builds a scenario-based `ConversationalGolden` and stamps the
category / severity / case-id / blocker tags into `additional_metadata` (the
DeepEval golden has no first-class severity field). The blocker set is verified
against the workbook's `Severity` column; `make_golden` cross-checks every
golden's severity against it so a mistagged case fails at import.
"""

from __future__ import annotations

from deepeval.dataset import ConversationalGolden

#: Workbook cluster letter -> human-readable category name (A-M).
CATEGORY_NAMES: dict[str, str] = {
    "A": "Retrieval Accuracy",
    "B": "Answer Grounding",
    "C": "Hallucination & Safety",
    "D": "Confidence & Escalation",
    "E": "Conversation Quality",
    "F": "Intent Routing",
    "G": "API Transactional",
    "H": "API Error Handling",
    "I": "Data Correctness",
    "J": "Multi-intent & Loop",
    "K": "Ticket & Handoff",
    "L": "Keywords & Session",
    "M": "Regression",
}

#: The 17 blocker cases, verified against the workbook Severity column. A single
#: blocker-golden failure holds the build (see evals/test_multiturn.py).
BLOCKER_CASE_IDS: frozenset[str] = frozenset(
    {
        # Phase 1 (10)
        "B3", "C1", "C2", "C3", "C5", "C6", "C7", "C8", "D3", "D4",
        # Phase 2 (7)
        "F7", "G1", "G5", "H8", "I1", "I2", "I3",
    }
)

VALID_SEVERITIES: frozenset[str] = frozenset({"blocker", "high", "medium", "low"})


def make_golden(
    *,
    case_id: str,
    severity: str,
    scenario: str,
    expected_outcome: str,
    user_description: str,
) -> ConversationalGolden:
    """Build a tagged, scenario-based `ConversationalGolden`.

    Tags land in `additional_metadata`: `case_id`, `category` (cluster letter),
    `category_name`, `severity`, `phase`, and `blocker`. Enforces that a case is
    tagged `blocker` iff it is in `BLOCKER_CASE_IDS`, so mistags fail at import.
    """
    category = case_id[0]
    if category not in CATEGORY_NAMES:
        raise ValueError(f"{case_id!r}: unknown category {category!r}")
    sev = severity.lower()
    if sev not in VALID_SEVERITIES:
        raise ValueError(f"{case_id!r}: invalid severity {severity!r}")
    is_blocker = sev == "blocker"
    if is_blocker != (case_id in BLOCKER_CASE_IDS):
        raise ValueError(
            f"{case_id!r}: severity/blocker-set mismatch "
            f"(severity={sev!r}, in_blocker_set={case_id in BLOCKER_CASE_IDS})"
        )
    phase = 1 if category in "ABCDE" else 2
    return ConversationalGolden(
        scenario=scenario,
        expected_outcome=expected_outcome,
        user_description=user_description,
        additional_metadata={
            "case_id": case_id,
            "category": category,
            "category_name": CATEGORY_NAMES[category],
            "severity": sev,
            "phase": phase,
            "blocker": is_blocker,
        },
    )
