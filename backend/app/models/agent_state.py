from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, UTCDateTime


class AgentState(Base):
    """Último estado conocido del PC (una sola fila, id = 1)."""

    __tablename__ = "agent_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    hostname: Mapped[str | None] = mapped_column(String(64), default=None)
    agent_version: Mapped[str | None] = mapped_column(String(32), default=None)
    pending_action: Mapped[str | None] = mapped_column(String(16), default=None)
    execute_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
