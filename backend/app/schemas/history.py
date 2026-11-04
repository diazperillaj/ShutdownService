from datetime import datetime

from .base import CamelModel


class HistoryEntryOut(CamelModel):
    id: int
    created_at: datetime
    source: str
    action: str
    delay_seconds: int | None
    result: str
    detail: str | None
