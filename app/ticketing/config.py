"""Typed loader for the ticketing-owned Freshdesk config (``freshdesk.yaml``).

Every Freshdesk field value the ticket builder needs is read from the bundled
``freshdesk.yaml`` (04 §5 DECISION: config-driven, no redeploy to swap a group or
turn on per-report Types). Secrets are NOT in the YAML — it names the env vars
(``FRESHDESK_API_KEY`` / ``FRESHDESK_API_ROOT``) which are resolved here at load
time so a leaked config file never carries a key.
"""

from __future__ import annotations

import functools
import os
import pathlib
from collections.abc import Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field

#: The bundled config file (ticketing-owned; NOT app/config/**).
CONFIG_PATH: pathlib.Path = pathlib.Path(__file__).with_name("freshdesk.yaml")


class DefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: int
    source: int
    status: int
    priority: int
    tags: list[str]
    language_tag_template: str
    subject_template: str
    transcript_last_n: int


class CustomFieldsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id_field: str
    product_field: str
    product: str
    query_type_field: str
    query_type: str
    query_sub_type_field: str
    query_sub_type: str
    source_field: str
    source_value: str


class TypeMapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    send_type: bool
    default: str
    by_intent: dict[str, str]


class SubjectSubTypeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str
    by_intent: dict[str, str]


class FreshdeskConfig(BaseModel):
    """The whole ticketing config, with secrets resolved from the environment.

    ``api_key`` / ``api_root`` are populated at load time from the env vars named
    by ``api_key_env`` / ``api_root_env`` — never stored in the YAML.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_key_env: str
    api_root_env: str
    api_root_default: str
    defaults: DefaultsConfig
    custom_fields: CustomFieldsConfig
    # ``type`` in the YAML; aliased so it does not shadow the builtin.
    type_map: TypeMapConfig = Field(alias="type")
    subject_sub_type: SubjectSubTypeConfig

    # Resolved at load time, not present in the YAML.
    api_key: str | None = None
    api_root: str | None = None


def load_config(
    path: pathlib.Path | None = None,
    env: Mapping[str, str] | None = None,
) -> FreshdeskConfig:
    """Load ``freshdesk.yaml`` and resolve the secret/env values.

    ``env`` defaults to ``os.environ``; tests pass an explicit mapping so no real
    secret is required. A missing ``FRESHDESK_API_ROOT`` falls back to
    ``api_root_default``; a missing ``FRESHDESK_API_KEY`` leaves ``api_key`` None
    (the client raises a clear config error rather than sending an anonymous call).
    """
    path = path or CONFIG_PATH
    env = os.environ if env is None else env
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["freshdesk"]
    cfg = FreshdeskConfig.model_validate(raw)
    return cfg.model_copy(
        update={
            "api_key": env.get(cfg.api_key_env),
            "api_root": (env.get(cfg.api_root_env) or cfg.api_root_default).rstrip("/"),
        }
    )


@functools.lru_cache(maxsize=1)
def default_config() -> FreshdeskConfig:
    """The process-wide default config (env-resolved, cached). Tests that need a
    hermetic config call ``load_config`` with an explicit ``env`` instead."""
    return load_config()
