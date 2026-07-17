"""Shared builders for the orchestrator suite."""

from __future__ import annotations

from app.config.defaults import DEFAULT_CONFIG
from app.contracts.rag import RagAnswer
from app.contracts.router import ExtractedParams, Intent, RouterResult
from app.contracts.wire import ChatRequest, ChipAction, FileCard, SessionContext
from app.llm.client import LLMClient
from app.orchestrator.orchestrator import Orchestrator
from app.orchestrator.ports import Services, StepResult
from tests.orchestrator.fakes import (
    FakeEngine,
    FakeLLM,
    FakeRag,
    FakeRouter,
    FakeStore,
    FakeTicketing,
)

USER_ID = "X008593"


def make_session(page: str = "support") -> SessionContext:
    return SessionContext.from_url_params(
        userId=USER_ID,
        sessionId="s-secret",
        accessToken="jwt-secret",
        isDarkTheme="false",
        platform="web",
        page=page,
    )


def seed_request(page: str = "support") -> ChatRequest:
    return ChatRequest(session=make_session(page), turn_number=0)


def turn_request(
    thread_id: str,
    *,
    message: str | None = None,
    action: ChipAction | None = None,
    page: str = "support",
) -> ChatRequest:
    return ChatRequest(
        session=make_session(page),
        thread_id=thread_id,
        message=message,
        action=action,
    )


def make_orchestrator(
    *,
    llm: FakeLLM | LLMClient | None = None,
    router: FakeRouter | None = None,
    engine: FakeEngine | None = None,
    rag: FakeRag | None = None,
    ticketing: FakeTicketing | None = None,
    store: FakeStore | None = None,
) -> tuple[Orchestrator, FakeStore]:
    """Build an Orchestrator wired to fakes; returns it plus the store for assertions."""
    store = store or FakeStore()
    services = Services(
        router=router or FakeRouter(RouterResult(intent=Intent.rag_qa)),
        engine=engine or FakeEngine(StepResult(blocks=[_default_file_card()])),
        rag=rag or FakeRag(RagAnswer(answer="An answer.")),
        ticketing=ticketing or FakeTicketing(),
    )
    orch = Orchestrator(
        services=services,
        store=store,
        llm=llm or FakeLLM(),
        config=DEFAULT_CONFIG,
    )
    return orch, store


def _default_file_card() -> FileCard:
    return FileCard(filename="P&L_Statement.pdf", size_label="182 KB", format="pdf")


def bootstrap(orch: Orchestrator, page: str = "support") -> str:
    """Run the session seed and return the minted thread_id."""
    resp = orch.handle_turn(seed_request(page))
    return resp.thread_id
