"""Drift guard for the checked-in tools JSON Schema (D15, task 3.4).

Regenerates the tool definitions and diffs against the committed
``app/contracts/schema/tools.schema.json`` — fails if a frozen model changed
without regenerating the schema.
"""

from __future__ import annotations

import pathlib

from app.contracts.tools import tools_schema_json

SCHEMA_PATH = pathlib.Path("app/contracts/schema/tools.schema.json")


def test_tools_schema_not_stale():
    committed = SCHEMA_PATH.read_text()
    regenerated = tools_schema_json()
    assert committed == regenerated, (
        "app/contracts/schema/tools.schema.json is stale — regenerate it with "
        "`python -m app.contracts.regen_schemas` and commit."
    )
