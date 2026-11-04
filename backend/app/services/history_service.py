from ..core.database import SessionFactory
from ..models import ActionLog, Result, Source
from ..realtime.panel_broadcaster import PanelBroadcaster
from ..repositories.action_log_repository import ActionLogRepository
from ..schemas.history import HistoryEntryOut
from ..schemas.realtime import HistoryEvent


class HistoryService:
    def __init__(self, sessions: SessionFactory, broadcaster: PanelBroadcaster) -> None:
        self._sessions = sessions
        self._broadcaster = broadcaster

    async def record(
        self,
        *,
        source: Source,
        action: str,
        result: Result,
        delay_seconds: int | None = None,
        detail: str | None = None,
        user_id: int | None = None,
    ) -> HistoryEntryOut:
        async with self._sessions() as db:
            entry = await ActionLogRepository(db).add(
                ActionLog(
                    source=source.value,
                    action=action,
                    result=result.value,
                    delay_seconds=delay_seconds,
                    detail=detail,
                    user_id=user_id,
                )
            )
            await db.commit()
        out = HistoryEntryOut.model_validate(entry)
        self._broadcaster.publish(HistoryEvent(data=out))
        return out

    async def list_recent(self, limit: int) -> list[HistoryEntryOut]:
        async with self._sessions() as db:
            rows = await ActionLogRepository(db).list_recent(limit)
        return [HistoryEntryOut.model_validate(row) for row in rows]
