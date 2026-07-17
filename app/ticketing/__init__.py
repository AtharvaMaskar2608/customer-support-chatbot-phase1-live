"""Server-side Freshdesk ticketing integration (ticketing-freshdesk capability).

All Freshdesk HTTP lives in this package behind the frozen render-block and
Intent contracts. The orchestrator binds ``raise_ticket`` / ``get_ticket_status``
by their frozen tool names via ``TICKETING_TOOLS``; the tool-registration surface
is completed in ``tool.py`` (see ``TICKETING_TOOLS`` below once implemented).
"""

from __future__ import annotations

from app.ticketing.config import FreshdeskConfig, load_config

__all__ = ["FreshdeskConfig", "load_config"]
