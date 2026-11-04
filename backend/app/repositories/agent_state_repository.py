from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentState

_SINGLE_ROW_ID = 1


class AgentStateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self) -> AgentState | None:
        return await self._db.get(AgentState, _SINGLE_ROW_ID)

    async def get_or_create(self) -> AgentState:
        row = await self.get()
        if row is None:
            row = AgentState(id=_SINGLE_ROW_ID)
            self._db.add(row)
        return row
