"""``FinXClient`` facade — composes the five per-backend adapters.

Realizes the frozen :class:`~app.finx.interfaces.FinXClient` Protocol: it exposes
one attribute per backend (``dotnet`` / ``go`` / ``mis`` / ``mf`` / ``coti``) and
constructs each adapter with the shared transport and the session's credentials,
so the orchestrator calls the facade and each endpoint routes to the adapter that
owns its backend with the correct credential forwarded. This is composition only
— no generic wrapper, no per-endpoint logic here.
"""

from __future__ import annotations

import httpx

from app.finx.adapters.base import DEFAULT_SETTINGS, HttpTransport, TransportSettings
from app.finx.adapters.coti import FinxOmneCotiAdapterImpl
from app.finx.adapters.credentials import FinXCredentials
from app.finx.adapters.dotnet import DotNetMiddlewareAdapterImpl
from app.finx.adapters.go import GoMiddlewareAdapterImpl
from app.finx.adapters.mf import MfProfileAdapterImpl
from app.finx.adapters.mis import MisReportsAdapterImpl


class FinXClientImpl:
    """Concrete :class:`~app.finx.interfaces.FinXClient` facade.

    The ``client`` is owned by the caller (one per session, closed by the caller);
    the facade never closes it. All five adapters share one :class:`HttpTransport`
    so the timeout/retry/logging policy is applied uniformly.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        credentials: FinXCredentials,
        *,
        settings: TransportSettings = DEFAULT_SETTINGS,
    ) -> None:
        transport = HttpTransport(client, settings=settings)
        self.dotnet = DotNetMiddlewareAdapterImpl(transport, credentials)
        self.go = GoMiddlewareAdapterImpl(transport, credentials)
        self.mis = MisReportsAdapterImpl(transport, credentials)
        self.mf = MfProfileAdapterImpl(transport, credentials)
        self.coti = FinxOmneCotiAdapterImpl(transport, credentials)
