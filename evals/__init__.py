"""Choice Jini evaluation harness (eval-harness capability).

The machine-runnable eval layer the spec prescribes (§7.4/§7.6): scenario-based
``ConversationalGolden``s, the ``ConversationSimulator`` model-callback plumbing,
the metric set with proposed thresholds, the ``claude-opus-4-8`` judge wrapper,
and the ``deepeval test run`` CI target that gates on blocker-severity cases.

This package is a *consumer* — it drives the app's public chat surface
(``POST /api/chat``) and maps responses into DeepEval objects. It defines no
product code and edits no other change's files.

Import side effect: DeepEval anonymous telemetry is opted out unless the operator
explicitly overrides it, so CI stays hermetic (no outbound calls at import).
"""

from __future__ import annotations

import os

# Keep CI hermetic: opt out of DeepEval's anonymous telemetry unless the operator
# has deliberately set the flag themselves. Set before deepeval is first imported.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

__all__ = ["THRESHOLDS_PATH"]

#: Single source of the proposed metric thresholds (decisions for review).
THRESHOLDS_PATH = os.path.join(os.path.dirname(__file__), "thresholds.yaml")
