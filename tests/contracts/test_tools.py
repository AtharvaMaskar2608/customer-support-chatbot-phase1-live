"""Agent tool-definition spec tests (specs/router-contract §Agent tool definitions).

Asserts the ten frozen tool names, top-level strict:true, input_schemas
generated in the strict subset (additionalProperties:false, full required, no
unsupported constraints, self-contained), and that `route` is built from
RouterResult.
"""

from __future__ import annotations

import json

from app.contracts.router import RouterResult
from app.contracts.tools import (
    TOOL_NAMES,
    TOOLS,
    TOOLS_BY_NAME,
    strict_input_schema,
)

EXPECTED_NAMES = (
    "route",
    "get_pnl_report",
    "get_ledger_report",
    "get_contract_notes",
    "get_tax_report",
    "get_cml",
    "get_brokerage_slabs",
    "search_kb",
    "raise_ticket",
    "get_ticket_status",
)

_UNSUPPORTED = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
}


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def test_tool_names_and_strict():
    assert TOOL_NAMES == EXPECTED_NAMES
    assert len(TOOLS) == 10
    for tool in TOOLS:
        assert tool.strict is True, tool.name
        schema = tool.input_schema
        # Strict subset: object with additionalProperties:false and full required.
        assert schema.get("type") == "object", tool.name
        assert schema["additionalProperties"] is False, tool.name
        assert set(schema["required"]) == set(schema.get("properties", {}).keys()), tool.name


def test_tool_schemas_are_strict_subset():
    for tool in TOOLS:
        blob = json.dumps(tool.input_schema)
        # Self-contained (inlined) — no $ref / $defs (no recursive schemas).
        assert "$ref" not in blob and "$defs" not in blob, tool.name
        # Every nested object also enforces the strict shape; no unsupported keywords.
        for node in _walk(tool.input_schema):
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(props.keys())
            assert _UNSUPPORTED.isdisjoint(node.keys()), (tool.name, node.keys() & _UNSUPPORTED)


def test_route_input_schema_from_router_result():
    route = TOOLS_BY_NAME["route"]
    assert set(route.input_schema["properties"].keys()) == set(RouterResult.model_fields.keys())
    # Regenerating from RouterResult yields the same strict schema.
    assert route.input_schema == strict_input_schema(RouterResult)


def test_ledger_tool_carries_mtf_flag():
    ledger = TOOLS_BY_NAME["get_ledger_report"]
    assert "mtf" in ledger.input_schema["properties"]
