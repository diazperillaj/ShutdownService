from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.error_handlers import register_error_handlers
from .api.router import api_router
from .core.config import Settings
from .core.database import create_db
from .core.logging import configure_logging
from .core.rate_limit import SlidingWindowLimiter
from .realtime.agent_connection import AgentConnection
from .realtime.panel_broadcaster import PanelBroadcaster
from .services.agent_service import AgentService
from .services.agent_state_service import AgentStateService
from .services.control_service import ControlService
from .services.history_service import HistoryService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fábrica de la aplicación. En producción: `uvicorn app.main:create_app --factory`."""
    settings = settings or Settings()
    configure_logging()

    engine, sessions = create_db(settings.database_url)
    broadcaster = PanelBroadcaster()
    state_service = AgentStateService(sessions, broadcaster)
    history_service = HistoryService(sessions, broadcaster)
    agent_service = AgentService(
        AgentConnection(settings.ack_timeout_seconds), state_service, history_service
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await state_service.load()
        yield
        await engine.dispose()

    app = FastAPI(
        title="ShutdownService",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.enable_docs else None,
    )
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.broadcaster = broadcaster
    app.state.state_service = state_service
    app.state.history_service = history_service
    app.state.agent_service = agent_service
    app.state.control_service = ControlService(agent_service, state_service, history_service)
    app.state.login_limiter = SlidingWindowLimiter(settings.login_ip_attempts_per_minute, 60)

    register_error_handlers(app)
    app.include_router(api_router)
    return app
