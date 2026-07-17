"""Native tool-use registry (router-contract capability, D15).

The complete frozen tool set as Anthropic tool definitions (``name``,
``description``, ``input_schema``, ``strict: true``). Jini uses native tool use
for every structured decision — NEVER prompt-then-parse-JSON. Every
``input_schema`` is generated from a frozen Pydantic model into the
strict-tool-use JSON Schema subset (``additionalProperties: false``, full
``required`` list, unsupported numeric/string/array constraints stripped and
enforced in application code instead), then dumped to the checked-in
``schema/tools.schema.json`` with a drift test.

Tool NAME strings are frozen; implementations bind at runtime via the
orchestrator's registry (engine / rag / ticketing changes). This module ships
definitions only.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.contracts.router import (
    DateRange,
    Delivery,
    RaiseTicketInput,
    ReportFormat,
    RouterResult,
    Segment,
    TicketStatusInput,
)

# ---------------------------------------------------------------------------
# Strict JSON Schema generation (structured-outputs-supported subset)
# ---------------------------------------------------------------------------

# JSON Schema keywords not supported by the strict tool-use subset. They are
# stripped from generated input_schemas and enforced in application/validation
# code after receipt instead. "title"/"default" are dropped as noise.
_UNSUPPORTED_KEYWORDS: frozenset[str] = frozenset(
    {
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
        "minProperties",
        "maxProperties",
        "title",
        "default",
    }
)


def _deref(node: Any, defs: dict[str, Any]) -> Any:
    """Inline every $ref against $defs so the schema is self-contained (no
    recursive schemas exist in the frozen models, so inlining terminates)."""
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            merged = _deref(copy.deepcopy(defs[name]), defs)
            for k, v in node.items():
                if k != "$ref":
                    merged[k] = _deref(v, defs)
            return merged
        return {k: _deref(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_deref(item, defs) for item in node]
    return node


def _strictify(node: Any) -> Any:
    """Drop unsupported keywords and, on every object, set
    ``additionalProperties: false`` and require every property (strict tool use
    requires all properties present; optional fields are modeled as nullable)."""
    if isinstance(node, dict):
        node = {k: v for k, v in node.items() if k not in _UNSUPPORTED_KEYWORDS}
        node = {k: _strictify(v) for k, v in node.items()}
        if node.get("type") == "object" or "properties" in node:
            props = node.get("properties", {})
            node["additionalProperties"] = False
            node["required"] = list(props.keys())
        return node
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    return node


def strict_input_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Generate a strict-tool-use ``input_schema`` from a frozen Pydantic model."""
    schema = model.model_json_schema(by_alias=True)
    defs = schema.pop("$defs", {})
    return _strictify(_deref(schema, defs))


# ---------------------------------------------------------------------------
# Tool input models (the fulfilment + retrieval tools)
# ---------------------------------------------------------------------------
# These carry only customer-facing parameters. FinX identity fields (LoginId,
# UserId, SessionId, client codes) bind server-side in the adapter layer and are
# never chosen by the model.


class PnlReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment: Segment
    date_range: DateRange
    delivery: Delivery = Delivery.in_chat


class LedgerReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_range: DateRange
    delivery: Delivery = Delivery.in_chat
    mtf: bool = False  # MTF Ledger flag


class ContractNotesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_range: DateRange


class TaxReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fy: str
    report_format: ReportFormat = ReportFormat.pdf
    delivery: Delivery = Delivery.in_chat


class CmlInput(BaseModel):
    # CML needs no user-chosen parameters; the client id binds from the session.
    model_config = ConfigDict(extra="forbid")


class BrokerageInput(BaseModel):
    # Brokerage slabs bind from the session; no user-chosen parameters.
    model_config = ConfigDict(extra="forbid")


class SearchKbInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str


# ---------------------------------------------------------------------------
# Tool definitions (frozen names)
# ---------------------------------------------------------------------------


class ToolDefinition(BaseModel):
    """An Anthropic native tool definition with a top-level ``strict`` flag."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict[str, Any]
    strict: bool = True


def _tool(name: str, description: str, model: type[BaseModel]) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        input_schema=strict_input_schema(model),
        strict=True,
    )


#: The ten frozen tools. `route` is the router's forced classification tool
#: (input_schema from RouterResult); the rest are fulfilment / retrieval /
#: ticketing tools whose implementations bind at runtime.
TOOLS: tuple[ToolDefinition, ...] = (
    _tool(
        "route",
        "Classify the user's utterance into an Intent with extracted parameters. "
        "The router forces this tool; RouterResult materializes from its input.",
        RouterResult,
    ),
    _tool(
        "get_pnl_report",
        "Fetch the customer's P&L Statement for a segment and date range and "
        "deliver it in chat or by email.",
        PnlReportInput,
    ),
    _tool(
        "get_ledger_report",
        "Fetch the customer's Ledger (or MTF Ledger when mtf=true) for a date "
        "range and deliver it in chat or by email.",
        LedgerReportInput,
    ),
    _tool(
        "get_contract_notes",
        "List the customer's contract notes for a date range for per-note download.",
        ContractNotesInput,
    ),
    _tool(
        "get_tax_report",
        "Fetch the customer's Tax Report for a financial year as PDF or Excel and "
        "deliver it in chat or by email. Capital Gain and Tax-P&L route here.",
        TaxReportInput,
    ),
    _tool(
        "get_cml",
        "Generate the customer's Client Master List (CML) document.",
        CmlInput,
    ),
    _tool(
        "get_brokerage_slabs",
        "Fetch the customer's brokerage slab card (rates per segment).",
        BrokerageInput,
    ),
    _tool(
        "search_kb",
        "Retrieve knowledge-base context to answer a process / how-to question.",
        SearchKbInput,
    ),
    _tool(
        "raise_ticket",
        "Raise a Freshdesk support ticket for the customer's query.",
        RaiseTicketInput,
    ),
    _tool(
        "get_ticket_status",
        "Look up the status of a previously raised support ticket.",
        TicketStatusInput,
    ),
)

#: The frozen tool-name strings (exactly ten).
TOOL_NAMES: tuple[str, ...] = tuple(t.name for t in TOOLS)

#: Tool lookup by name.
TOOLS_BY_NAME: dict[str, ToolDefinition] = {t.name: t for t in TOOLS}


def tools_schema_json() -> str:
    """Deterministic serialization of all tool definitions for the checked-in file."""
    payload = [t.model_dump() for t in sorted(TOOLS, key=lambda t: t.name)]
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
