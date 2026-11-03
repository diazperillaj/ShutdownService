from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, UTCDateTime, utcnow


class Action(StrEnum):
    SHUTDOWN = "shutdown"
    RESTART = "restart"
    SLEEP = "sleep"
    HIBERNATE = "hibernate"
    LOCK = "lock"


# Acciones que admiten temporizador; bloquear solo es inmediata.
PROGRAMMABLE_ACTIONS = frozenset(Action) - {Action.LOCK}


class Source(StrEnum):
    WEB = "web"
    ALEXA = "alexa"
    AGENT = "agent"


class Result(StrEnum):
    OK = "ok"
    ERROR = "error"
    OFFLINE = "offline"
    TIMEOUT = "timeout"
    EXECUTED = "executed"
    DISCARDED = "discarded"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Solo se guarda el hash SHA-256 del token; el token en claro vive en la cookie.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(256), default=None)


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
