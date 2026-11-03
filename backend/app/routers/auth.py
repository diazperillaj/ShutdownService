from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import SESSION_COOKIE, Authenticated, current_auth, require_same_origin
from ..config import Settings
from ..db import get_db, utcnow
from ..models import User, UserSession
from ..schemas import ChangePasswordIn, LoginIn, UserOut
from ..security import (
    MIN_PASSWORD_LENGTH,
    burn_password_check,
    hash_password,
    hash_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_INVALID_CREDENTIALS = "Usuario o contraseña incorrectos"
_TOO_MANY_ATTEMPTS = "Demasiados intentos. Intenta de nuevo más tarde"


def _client_ip(request: Request) -> str:
    # Uvicorn reemplaza request.client con la IP real cuando la petición llega desde el proxy de confianza.
    return request.client.host if request.client else "desconocida"


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/login", response_model=UserOut, dependencies=[Depends(require_same_origin)])
async def login(
    body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> UserOut:
    settings: Settings = request.app.state.settings
    ip = _client_ip(request)
    if not request.app.state.login_limiter.hit(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _TOO_MANY_ATTEMPTS)

    user = await db.scalar(select(User).where(User.username == body.username))
    if user is None:
        await run_in_threadpool(burn_password_check, body.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_CREDENTIALS)

    now = utcnow()
    if user.locked_until is not None and user.locked_until > now:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _TOO_MANY_ATTEMPTS)

    if not await run_in_threadpool(verify_password, user.password_hash, body.password):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.login_max_attempts:
            user.failed_attempts = 0
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_CREDENTIALS)

    user.failed_attempts = 0
    user.locked_until = None
    if password_needs_rehash(user.password_hash):
        user.password_hash = await run_in_threadpool(hash_password, body.password)

    token = new_session_token()
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
            ip=ip,
            user_agent=(request.headers.get("user-agent") or "")[:256] or None,
        )
    )
    await db.commit()
    _set_session_cookie(response, token, settings)
    return UserOut(username=user.username)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_same_origin)]
)
async def logout(
    request: Request,
    response: Response,
    auth: Authenticated = Depends(current_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(delete(UserSession).where(UserSession.id == auth.session.id))
    await db.commit()
    settings: Settings = request.app.state.settings
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, secure=settings.cookie_secure, samesite="strict"
    )


@router.get("/me", response_model=UserOut)
async def me(auth: Authenticated = Depends(current_auth)) -> UserOut:
    return UserOut(username=auth.user.username)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
async def change_password(
    body: ChangePasswordIn,
    auth: Authenticated = Depends(current_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    if len(body.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"La nueva contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres",
        )
    user = await db.get(User, auth.user.id)
    if user is None or not await run_in_threadpool(
        verify_password, user.password_hash, body.current_password
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta")

    user.password_hash = await run_in_threadpool(hash_password, body.new_password)
    # Cierra todas las demás sesiones abiertas.
    await db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id, UserSession.id != auth.session.id
        )
    )
    await db.commit()
