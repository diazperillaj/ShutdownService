from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ActionLog


class ActionLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, entry: ActionLog) -> ActionLog:
        self._db.add(entry)
        await self._db.flush()  # asigna id y created_at
        return entry

    async def list_recent(self, limit: int) -> Sequence[ActionLog]:
        rows = await self._db.scalars(
            select(ActionLog).order_by(ActionLog.created_at.desc(), ActionLog.id.desc()).limit(limit)
        )
        return rows.all()
