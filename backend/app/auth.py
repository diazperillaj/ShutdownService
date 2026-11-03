from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db, utcnow
from .models import User, UserSession
from .security import hash_token

SESSION_COOKIE = "ss_session"
# Cada cuánto se actualiza last_seen_at para no escribir en cada petición.
_LAST_SEEN_RESOLUTION = timedelta(minutes=5)


@dataclass(frozen=True)
class Authenticated:
    user: User
    session: UserSession


async def resolve_session(db: AsyncSession, token: str) -> Authenticated | None:
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        return None
    session, user = row
    now = utcnow()
    if session.expires_at <= now:
        await db.delete(session)
        await db.commit()
        return None
    if now - session.last_seen_at > _LAST_SEEN_RESOLUTION:
        session.last_seen_at = now
        await db.commit()
    return Authenticated(user=user, session=session)


async def current_auth(request: Request, db: AsyncSession = Depends(get_db)) -> Authenticated:
    token = request.cookies.get(SESSION_COOKIE)
    auth = await resolve_session(db, token) if token else None
    if auth is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no válida")
    return auth


async def current_user(auth: Authenticated = Depends(current_auth)) -> User:
    return auth.user


async def require_same_origin(request: Request) -> None:
    """Protección CSRF: las peticiones que modifican datos deben venir del propio panel."""
    if request.headers.get("origin") != request.app.state.settings.public_origin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origen no permitido")
