from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, UTCDateTime, utcnow


class ActionLog(Base):
    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    delay_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    result: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str | None] = mapped_column(String(256), default=None)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
