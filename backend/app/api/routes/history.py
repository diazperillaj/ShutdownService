from fastapi import APIRouter, Depends, Query

from ...schemas.history import HistoryEntryOut
from ...services.history_service import HistoryService
from ..deps import current_user, get_history_service

router = APIRouter(prefix="/api", tags=["history"], dependencies=[Depends(current_user)])


@router.get("/history", response_model=list[HistoryEntryOut])
async def history(
    limit: int = Query(50, ge=1, le=200),
    history_service: HistoryService = Depends(get_history_service),
) -> list[HistoryEntryOut]:
    return await history_service.list_recent(limit)
