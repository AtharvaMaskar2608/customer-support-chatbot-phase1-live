"""Optional synthetic RAG-golden seeding (eval-harness capability).

A seeding *aid*, not a build step. It uses DeepEval's `Synthesizer` to expand the
single-turn RAG golden set from `qa_chunks` contexts (the pre-populated KB), so an
author has draft `(input, expected_output, context)` goldens to review rather than
writing every retriever case from a blank page.

Wave-1 note — OFF by default, never run in CI. Two properties keep it hermetic:

  * Import is side-effect-free: no `Synthesizer`, no DB, and no network at import
    (the `Synthesizer` and its judge are built lazily, inside the functions).
  * There is no default context source. Contexts are passed in, or an explicit
    `ContextSource` is injected — mirroring the simulator's driver seam — so
    nothing here reaches Postgres until Wave 2 wires a real source.
    `get_default_context_source()` refuses to run until one is set.

The no-replay rule still holds: `Synthesizer` output is *scenario/label seed
material*, reviewed and hand-authored into `evals/goldens/` — never dumped in
verbatim and never seeded from production transcripts.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from evals.judge import build_judge


@runtime_checkable
class ContextSource(Protocol):
    """Supplies grounding contexts (each a list of `qa_chunks` texts) to seed from.

    Injected, never defaulted in Wave 1 — the concrete source that reads the
    `qa_chunks` KB is wired in Wave 2 so this module makes no DB call in CI.
    """

    def __call__(self, limit: int) -> list[list[str]]: ...


_DEFAULT_CONTEXT_SOURCE: ContextSource | None = None


def set_default_context_source(source: ContextSource | None) -> None:
    """Configure the context source `seed_from_qa_chunks` uses (Wave 2 sets it)."""
    global _DEFAULT_CONTEXT_SOURCE
    _DEFAULT_CONTEXT_SOURCE = source


def get_default_context_source() -> ContextSource:
    if _DEFAULT_CONTEXT_SOURCE is None:
        raise RuntimeError(
            "No qa_chunks context source configured. Wave-1 keeps synthetic seeding "
            "off and DB-free; inject a source via set_default_context_source() (e.g. "
            "one that selects chunk texts from the qa_chunks KB) before seeding in "
            "Wave 2."
        )
    return _DEFAULT_CONTEXT_SOURCE


def build_synthesizer(judge: Any = None) -> Any:
    """Build a DeepEval `Synthesizer` driven by the eval judge model.

    Lazy import so the module stays import-clean in CI. The judge defaults to the
    `claude-opus-4-8` wrapper — the same independent model used for evaluation.
    """
    from deepeval.synthesizer import Synthesizer

    return Synthesizer(model=judge if judge is not None else build_judge())


def generate_rag_goldens_from_contexts(
    contexts: list[list[str]],
    *,
    judge: Any = None,
    include_expected_output: bool = True,
    max_goldens_per_context: int = 2,
) -> list[Any]:
    """Generate single-turn RAG goldens from explicit grounding contexts.

    Thin wrapper over `Synthesizer.generate_goldens_from_contexts`. `contexts` is a
    list of context groups (each a list of `qa_chunks` texts); output goldens carry
    a synthesized `input` (raw query) and, when `include_expected_output`, a
    labelled `expected_output` for the ContextualPrecision/Recall metrics.
    """
    synthesizer = build_synthesizer(judge)
    return synthesizer.generate_goldens_from_contexts(
        contexts=contexts,
        include_expected_output=include_expected_output,
        max_goldens_per_context=max_goldens_per_context,
    )


def seed_from_qa_chunks(
    *,
    source: ContextSource | None = None,
    limit: int = 50,
    judge: Any = None,
    include_expected_output: bool = True,
    max_goldens_per_context: int = 2,
) -> list[Any]:
    """Seed RAG goldens from the `qa_chunks` KB via an injected context source.

    `source` defaults to the configured default (Wave 2); it must be set explicitly
    or via `set_default_context_source()` — there is no built-in DB access here, so
    this never touches Postgres in CI.
    """
    resolved = source or get_default_context_source()
    contexts = resolved(limit)
    return generate_rag_goldens_from_contexts(
        contexts,
        judge=judge,
        include_expected_output=include_expected_output,
        max_goldens_per_context=max_goldens_per_context,
    )


__all__ = [
    "ContextSource",
    "set_default_context_source",
    "get_default_context_source",
    "build_synthesizer",
    "generate_rag_goldens_from_contexts",
    "seed_from_qa_chunks",
]
