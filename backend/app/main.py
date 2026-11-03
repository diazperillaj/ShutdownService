import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .agent_hub import AgentHub
from .config import Settings
from .control import ControlError, ControlService
from .db import create_db
from .routers import auth, control, ws
from .security import SlidingWindowLimiter


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fábrica de la aplicación. En producción: `uvicorn app.main:create_app --factory`."""
    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    engine, sessionmaker = create_db(settings.database_url)
    hub = AgentHub(sessionmaker, settings.ack_timeout_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await hub.load()
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
    app.state.sessionmaker = sessionmaker
    app.state.hub = hub
    app.state.control = ControlService(hub)
    app.state.login_limiter = SlidingWindowLimiter(settings.login_ip_attempts_per_minute, 60)

    @app.exception_handler(ControlError)
    async def _control_error(request: Request, exc: ControlError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(control.router)
    app.include_router(ws.router)
    return app
