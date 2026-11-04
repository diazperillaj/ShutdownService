from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, UserSession


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: int) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        return await self._db.scalar(select(User).where(User.username == username))

    async def count(self) -> int:
        return await self._db.scalar(select(func.count()).select_from(User)) or 0

    def add(self, user: User) -> None:
        self._db.add(user)


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_with_user(self, token_hash: str) -> tuple[UserSession, User] | None:
        row = (
            await self._db.execute(
                select(UserSession, User)
                .join(User, User.id == UserSession.user_id)
                .where(UserSession.token_hash == token_hash)
            )
        ).first()
        return None if row is None else (row[0], row[1])

    def add(self, session: UserSession) -> None:
        self._db.add(session)

    async def delete(self, session_id: int) -> None:
        await self._db.execute(delete(UserSession).where(UserSession.id == session_id))

    async def delete_expired(self, now: datetime) -> int:
        """Borra las sesiones vencidas. Devuelve cuántas eran."""
        result = await self._db.execute(delete(UserSession).where(UserSession.expires_at <= now))
        return result.rowcount or 0

    async def delete_for_user(self, user_id: int, *, except_id: int | None = None) -> None:
        statement = delete(UserSession).where(UserSession.user_id == user_id)
        if except_id is not None:
            statement = statement.where(UserSession.id != except_id)
        await self._db.execute(statement)
