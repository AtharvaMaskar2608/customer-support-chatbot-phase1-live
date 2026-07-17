"""FastAPI app — POST /api/chat + session bootstrap (conversation-orchestrator).

Sole owner of ``app/main.py`` after contracts-foundation. Wires the FastAPI app,
the lifespan (startup/shutdown hook registry + Phase-1 tracing config), and the
single ``POST /api/chat`` route to the ``Orchestrator``:

  * first turn (``thread_id`` absent) → the session seed (greeting + entry chips +
    ``config_slice``), preserved verbatim from the contracts-foundation stub;
  * every later turn → the per-turn pipeline (agentic loop / deterministic dispatch),
    caps, sticky-language, fan-out + tracing.

The store-writer (#13) and tracing (#14) changes contribute startup hooks via the
lifecycle registry (``app.orchestrator.lifecycle``); they SHALL NOT edit this file.

``select_greeting`` is re-exported here so the frozen ``test_main_stub`` (which
imports it from ``app.main``) stays green; its source of truth is
``app.orchestrator.bootstrap``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config.defaults import DEFAULT_CONFIG
from app.contracts.tracing import trace_manager
from app.contracts.wire import ChatRequest
from app.llm.client import LLMClient
from app.orchestrator.bootstrap import build_config_slice, select_greeting  # re-exported
from app.orchestrator.defaults import (
    DefaultEngine,
    DefaultRag,
    DefaultRouter,
    DefaultTicketing,
    InMemoryStore,
)
from app.orchestrator.lifecycle import on_startup, run_shutdown, run_startup
from app.orchestrator.orchestrator import Orchestrator
from app.orchestrator.ports import Services

__all__ = ["app", "select_greeting", "build_config_slice", "build_orchestrator"]


@on_startup
def _configure_default_tracing() -> None:
    """Phase-1 default tracing config (offline; no Confident AI key). tracing (#14)
    may register a richer ``configure`` through the same lifecycle seam."""
    trace_manager.configure(environment="development")


def build_orchestrator() -> Orchestrator:
    """Construct the default Orchestrator with Phase-1 in-memory adapters + a real
    (lazily-constructed, network-free until called) LLM client."""
    services = Services(
        router=DefaultRouter(),
        engine=DefaultEngine(),
        rag=DefaultRag(),
        ticketing=DefaultTicketing(),
    )
    return Orchestrator(
        services=services,
        store=InMemoryStore(),
        llm=LLMClient(),
        config=DEFAULT_CONFIG,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup()
    yield
    await run_shutdown()


app = FastAPI(title="Choice Jini", version="0.1.0", lifespan=lifespan)
_orchestrator = build_orchestrator()


@app.post("/api/chat")
def chat(request: ChatRequest) -> JSONResponse:
    """Phase-1 non-streaming chat turn (one JSON per turn). Serialized by alias
    (note-list ``downloadToken``) and ``mode=json`` (enums/dates)."""
    response = _orchestrator.handle_turn(request)
    return JSONResponse(content=response.model_dump(by_alias=True, mode="json"))
