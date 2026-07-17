"""Offline structural tests for the golden set (eval-harness capability).

Runs in CI with no app, no judge key, and no network. Asserts what the proposal
promised about the authored goldens: the count floor, A-M coverage, the exact
blocker set, threshold-file completeness, and the no-historical-replay
anti-pattern guard. Part of the `pytest evals/ -k "goldens or callback"` gate.
"""

from __future__ import annotations

import os
import re

import pytest

from evals.goldens import (
    ALL_GOLDENS,
    assert_blocker_coverage,
    blocker_goldens,
    case_id,
    goldens_by_category,
    is_blocker,
)
from evals.goldens._catalog import (
    BLOCKER_CASE_IDS,
    CATEGORY_NAMES,
    VALID_SEVERITIES,
)
from evals.metrics import (
    blocker_safety_metric,
    conversational_metrics,
    rag_singleturn_metrics,
)

REQUIRED_METADATA = {"case_id", "category", "category_name", "severity", "phase", "blocker"}

#: Code-level replay constructs forbidden in the goldens package. Goldens must be
#: scenario-based ConversationalGoldens — never pre-baked transcripts (`turns=`),
#: prior test cases, or anything read from a conversation-log file. (Documentation
#: prose about the rule is fine; these patterns are actual replay code.)
FORBIDDEN_REPLAY_PATTERNS = [
    r"\bturns\s*=",
    r"\bmessages\s*=",
    r"ConversationalTestCase\s*\(",
    r"\bopen\s*\(",
    r"read_text\s*\(",
    r"json\.load",
    r"\bcsv\.",
    r"\.jsonl\b",
]


def test_min_golden_count():
    """At least 20 ConversationalGoldens exist (proposal floor)."""
    assert len(ALL_GOLDENS) >= 20, f"only {len(ALL_GOLDENS)} goldens; need >= 20"


def test_all_categories_covered():
    """Every workbook cluster A-M has at least one golden."""
    counts = {k: len(v) for k, v in goldens_by_category().items()}
    empty = sorted(k for k, n in counts.items() if n == 0)
    assert not empty, f"clusters with no goldens: {empty}"
    assert set(counts) == set(CATEGORY_NAMES), "category set drifted from A-M"


def test_blocker_set_is_exact():
    """The authored blocker goldens match the 17 canonical blocker case ids."""
    assert_blocker_coverage()  # raises on any missing/extra
    authored = {case_id(g) for g in blocker_goldens()}
    assert authored == set(BLOCKER_CASE_IDS)
    assert len(BLOCKER_CASE_IDS) == 17


def test_every_golden_is_well_tagged():
    """Each golden carries the full metadata tag set with valid values."""
    seen_ids: set[str] = set()
    for g in ALL_GOLDENS:
        meta = g.additional_metadata or {}
        missing = REQUIRED_METADATA - set(meta)
        assert not missing, f"{meta.get('case_id')}: missing metadata {sorted(missing)}"
        cid = meta["case_id"]
        assert cid not in seen_ids, f"duplicate case_id {cid}"
        seen_ids.add(cid)
        assert meta["category"] in CATEGORY_NAMES
        assert meta["severity"] in VALID_SEVERITIES
        assert meta["phase"] in (1, 2)
        # severity/blocker flag must agree with the canonical set
        assert bool(meta["blocker"]) == (cid in BLOCKER_CASE_IDS) == is_blocker(g)


def test_thresholds_yaml_is_complete():
    """Every threshold the metrics need is present in thresholds.yaml.

    Constructing the metric factories offline reads each key; a missing key raises
    KeyError at construction, so a green build proves the file is complete. No
    judge key needed — load_model() is a no-op.
    """
    conv = conversational_metrics()
    assert len(conv) == 11
    assert len(rag_singleturn_metrics()) == 3
    assert len(rag_singleturn_metrics(with_labels=True)) == 5
    assert blocker_safety_metric().strict_mode is True


def test_goldens_are_scenario_based_not_transcripts():
    """Semantic no-replay guard: no golden carries a pre-supplied transcript.

    A scenario-based ConversationalGolden has `turns` unset; a populated `turns`
    would be a replayed conversation.
    """
    offenders = [case_id(g) for g in ALL_GOLDENS if getattr(g, "turns", None)]
    assert not offenders, f"goldens with pre-supplied turns (replay): {offenders}"
    for g in ALL_GOLDENS:
        assert (g.scenario or "").strip(), f"{case_id(g)}: empty scenario"
        assert (g.expected_outcome or "").strip(), f"{case_id(g)}: empty expected_outcome"


def test_no_replay_code_in_goldens_package():
    """CI anti-pattern guard: the goldens package contains no transcript-replay code."""
    goldens_dir = os.path.join(os.path.dirname(__file__), "goldens")
    violations: list[str] = []
    for name in sorted(os.listdir(goldens_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(goldens_dir, name), encoding="utf-8") as fh:
            source = fh.read()
        for pattern in FORBIDDEN_REPLAY_PATTERNS:
            if re.search(pattern, source):
                violations.append(f"{name}: matched forbidden replay pattern /{pattern}/")
    assert not violations, "replay constructs found in goldens/: " + "; ".join(violations)
