import asyncio
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings
from ..core.constants import MIN_PASSWORD_LENGTH
from ..core.database import utcnow
from ..core.errors import (
    AppError,
    Conflict,
    InvalidCredentials,
    InvalidRequest,
    NotFound,
    TooManyAttempts,
)
from ..core.rate_limit import SlidingWindowLimiter
from ..core.security import (
    burn_password_check,
    hash_password,
    hash_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)
from ..models import User, UserSession
from ..repositories.user_repository import SessionRepository, UserRepository

_INVALID_CREDENTIALS = "Usuario o contraseña incorrectos"
_TOO_MANY_ATTEMPTS = "Demasiados intentos. Intenta de nuevo más tarde"
# Cada cuánto se actualiza last_seen_at para no escribir en cada petición.
_LAST_SEEN_RESOLUTION = timedelta(minutes=5)


class WrongCurrentPassword(AppError):
    status_code = 400


@dataclass(frozen=True)
class Authenticated:
    user: User
    session: UserSession


@dataclass(frozen=True)
class LoginResult:
    user: User
    token: str


def _validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidRequest(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._limiter = limiter
        self._users = UserRepository(db)
        self._sessions = SessionRepository(db)

    async def login(
        self, username: str, password: str, *, ip: str, user_agent: str | None
    ) -> LoginResult:
        if self._limiter is not None and not self._limiter.hit(ip):
            raise TooManyAttempts(_TOO_MANY_ATTEMPTS)

        user = await self._users.get_by_username(username)
        if user is None:
            await asyncio.to_thread(burn_password_check, password)
            raise InvalidCredentials(_INVALID_CREDENTIALS)

        now = utcnow()
        if user.locked_until is not None and user.locked_until > now:
            raise TooManyAttempts(_TOO_MANY_ATTEMPTS)

        if not await asyncio.to_thread(verify_password, user.password_hash, password):
            user.failed_attempts += 1
            if user.failed_attempts >= self._settings.login_max_attempts:
                user.failed_attempts = 0
                user.locked_until = now + timedelta(minutes=self._settings.login_lockout_minutes)
            await self._db.commit()
            raise InvalidCredentials(_INVALID_CREDENTIALS)

        user.failed_attempts = 0
        user.locked_until = None
        if password_needs_rehash(user.password_hash):
            user.password_hash = await asyncio.to_thread(hash_password, password)

        # Aprovecha el login para limpiar las sesiones vencidas; nada más las borra.
        await self._sessions.delete_expired(now)

        token = new_session_token()
        self._sessions.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user.id,
                expires_at=now + timedelta(hours=self._settings.session_ttl_hours),
                ip=ip,
                user_agent=(user_agent or "")[:256] or None,
            )
        )
        await self._db.commit()
        return LoginResult(user=user, token=token)

    async def resolve_session(self, token: str) -> Authenticated | None:
        found = await self._sessions.get_with_user(hash_token(token))
        if found is None:
            return None
        session, user = found
        now = utcnow()
        if session.expires_at <= now:
            await self._sessions.delete(session.id)
            await self._db.commit()
            return None
        if now - session.last_seen_at > _LAST_SEEN_RESOLUTION:
            session.last_seen_at = now
            await self._db.commit()
        return Authenticated(user=user, session=session)

    async def logout(self, auth: Authenticated) -> None:
        await self._sessions.delete(auth.session.id)
        await self._db.commit()

    async def change_password(
        self, auth: Authenticated, current_password: str, new_password: str
    ) -> None:
        _validate_new_password(new_password)
        user = await self._users.get(auth.user.id)
        if user is None or not await asyncio.to_thread(
            verify_password, user.password_hash, current_password
        ):
            raise WrongCurrentPassword("La contraseña actual no es correcta")
        user.password_hash = await asyncio.to_thread(hash_password, new_password)
        # Cierra todas las demás sesiones abiertas.
        await self._sessions.delete_for_user(user.id, except_id=auth.session.id)
        await self._db.commit()

    # --- Administración (CLI) ---

    async def ensure_can_create_user(self) -> None:
        if await self._users.count():
            raise Conflict("Ya existe un usuario. Usa set-password para cambiar su contraseña")

    async def ensure_user_exists(self, username: str) -> None:
        if await self._users.get_by_username(username) is None:
            raise NotFound(f"No existe el usuario '{username}'")

    async def create_user(self, username: str, password: str) -> User:
        """Crea el único usuario del panel."""
        await self.ensure_can_create_user()
        _validate_new_password(password)
        user = User(username=username, password_hash=await asyncio.to_thread(hash_password, password))
        self._users.add(user)
        await self._db.commit()
        return user

    async def reset_password(self, username: str, password: str) -> None:
        """Cambia la contraseña, desbloquea al usuario y cierra todas sus sesiones."""
        user = await self._users.get_by_username(username)
        if user is None:
            raise NotFound(f"No existe el usuario '{username}'")
        _validate_new_password(password)
        user.password_hash = await asyncio.to_thread(hash_password, password)
        user.failed_attempts = 0
        user.locked_until = None
        await self._sessions.delete_for_user(user.id)
        await self._db.commit()
