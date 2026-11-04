"""Dependencias de FastAPI: base de datos, servicios, sesión del usuario y protección CSRF."""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings
from ..core.database import SessionFactory
from ..core.errors import Forbidden, NotAuthenticated
from ..models import User
from ..realtime.panel_broadcaster import PanelBroadcaster
from ..services.agent_service import AgentService
from ..services.auth_service import Authenticated, AuthService
from ..services.control_service import ControlService
from ..services.history_service import HistoryService

SESSION_COOKIE = "ss_session"


def get_settings(conn: HTTPConnection) -> Settings:
    return conn.app.state.settings


def get_session_factory(conn: HTTPConnection) -> SessionFactory:
    return conn.app.state.sessions


def get_control_service(conn: HTTPConnection) -> ControlService:
    return conn.app.state.control_service


def get_history_service(conn: HTTPConnection) -> HistoryService:
    return conn.app.state.history_service


def get_agent_service(conn: HTTPConnection) -> AgentService:
    return conn.app.state.agent_service


def get_broadcaster(conn: HTTPConnection) -> PanelBroadcaster:
    return conn.app.state.broadcaster


async def get_db(
    sessions: SessionFactory = Depends(get_session_factory),
) -> AsyncIterator[AsyncSession]:
    async with sessions() as db:
        yield db


def get_auth_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(db, settings, request.app.state.login_limiter)


async def current_auth(
    request: Request, auth_service: AuthService = Depends(get_auth_service)
) -> Authenticated:
    token = request.cookies.get(SESSION_COOKIE)
    auth = await auth_service.resolve_session(token) if token else None
    if auth is None:
        raise NotAuthenticated("Sesión no válida")
    return auth


async def current_user(auth: Authenticated = Depends(current_auth)) -> User:
    return auth.user


async def require_same_origin(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    """Protección CSRF: las peticiones que modifican datos deben venir del propio panel."""
    if request.headers.get("origin") != settings.public_origin:
        raise Forbidden("Origen no permitido")


async def authenticate_websocket(conn: HTTPConnection) -> Authenticated | None:
    """Valida la sesión de un WebSocket con una conexión a la BD que se libera enseguida."""
    token = conn.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    async with get_session_factory(conn)() as db:
        return await AuthService(db, get_settings(conn)).resolve_session(token)
