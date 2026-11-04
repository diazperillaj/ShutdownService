from fastapi import APIRouter, Depends, Request, Response, status

from ...core.config import Settings
from ...schemas.auth import ChangePasswordIn, LoginIn, UserOut
from ...services.auth_service import Authenticated, AuthService
from ..deps import (
    SESSION_COOKIE,
    current_auth,
    get_auth_service,
    get_settings,
    require_same_origin,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # Uvicorn reemplaza request.client con la IP real cuando la petición llega desde el proxy de confianza.
    return request.client.host if request.client else "desconocida"


@router.post("/login", response_model=UserOut, dependencies=[Depends(require_same_origin)])
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    result = await auth_service.login(
        body.username,
        body.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        SESSION_COOKIE,
        result.token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return UserOut(username=result.user.username)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_same_origin)]
)
async def logout(
    response: Response,
    auth: Authenticated = Depends(current_auth),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> None:
    await auth_service.logout(auth)
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
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    await auth_service.change_password(auth, body.current_password, body.new_password)
