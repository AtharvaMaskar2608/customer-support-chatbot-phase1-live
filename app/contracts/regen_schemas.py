"""Regenerate the checked-in JSON Schemas from the frozen Pydantic models.

Run with ``python -m app.contracts.regen_schemas`` after changing the wire union
or a tool input model, then commit the updated ``schema/*.json`` files. Drift
tests fail if the committed files are stale.
"""

from __future__ import annotations

import pathlib

_SCHEMA_DIR = pathlib.Path(__file__).parent / "schema"


def regen_all() -> list[pathlib.Path]:
    """Rewrite every generated schema file. Returns the paths written."""
    from app.contracts.tools import tools_schema_json
    from app.contracts.wire import wire_schema_json

    written: list[pathlib.Path] = []

    wire_path = _SCHEMA_DIR / "chat_wire.schema.json"
    wire_path.write_text(wire_schema_json())
    written.append(wire_path)

    tools_path = _SCHEMA_DIR / "tools.schema.json"
    tools_path.write_text(tools_schema_json())
    written.append(tools_path)

    return written


if __name__ == "__main__":  # pragma: no cover
    for p in regen_all():
        print("wrote", p)
