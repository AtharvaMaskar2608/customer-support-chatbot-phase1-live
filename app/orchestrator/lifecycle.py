"""Startup/shutdown hook registry — the seam other changes register into.

``app/main.py``'s FastAPI lifespan runs these hooks. The store-writer (#13) and
tracing (#14) changes expose start/stop hooks that ONLY this change calls from
``main.py``; they register here (at import time) instead of editing ``main.py``.
Hooks may be sync or async.
"""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable, Union

Hook = Callable[[], Union[Awaitable[None], None]]

_startup_hooks: list[Hook] = []
_shutdown_hooks: list[Hook] = []


def on_startup(fn: Hook) -> Hook:
    """Register a startup hook (returns ``fn`` so it can be used as a decorator)."""
    _startup_hooks.append(fn)
    return fn


def on_shutdown(fn: Hook) -> Hook:
    """Register a shutdown hook (returns ``fn`` so it can be used as a decorator)."""
    _shutdown_hooks.append(fn)
    return fn


def clear_hooks() -> None:
    """Drop every registered hook (test isolation helper)."""
    _startup_hooks.clear()
    _shutdown_hooks.clear()


async def _run(hooks: list[Hook]) -> None:
    for fn in list(hooks):
        outcome = fn()
        if inspect.isawaitable(outcome):
            await outcome


async def run_startup() -> None:
    await _run(_startup_hooks)


async def run_shutdown() -> None:
    await _run(_shutdown_hooks)
