"""Drift guard for the checked-in wire JSON Schema (D11, task 2.5).

Regenerates the schema from the Pydantic wire union and diffs it against the
committed ``app/contracts/schema/chat_wire.schema.json``. Fails if the committed
schema is stale — this is the seam that keeps the widget's generated TypeScript
types in lockstep with the Python models.
"""

from __future__ import annotations

import pathlib

from app.contracts.wire import wire_schema_json

SCHEMA_PATH = pathlib.Path("app/contracts/schema/chat_wire.schema.json")


def test_chat_wire_schema_not_stale():
    committed = SCHEMA_PATH.read_text()
    regenerated = wire_schema_json()
    assert committed == regenerated, (
        "app/contracts/schema/chat_wire.schema.json is stale — regenerate it with "
        "`python -m app.contracts.regen_schemas` and commit."
    )
