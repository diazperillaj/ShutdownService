from datetime import datetime

from pydantic import Field, model_validator

from ..core.constants import MAX_DELAY_SECONDS
from ..models import Action
from .base import CamelModel


class ScheduleIn(CamelModel):
    action: Action
    delay_seconds: int | None = None
    # Hora concreta con zona horaria; el servicio la convierte en segundos.
    at: datetime | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "ScheduleIn":
        if (self.delay_seconds is None) == (self.at is None):
            raise ValueError("Indica delaySeconds o at, pero no ambos")
        if self.at is not None and self.at.tzinfo is None:
            raise ValueError("La hora debe incluir zona horaria")
        return self


class ExtendIn(CamelModel):
    seconds: int = Field(ge=60, le=MAX_DELAY_SECONDS)


class ActionNowIn(CamelModel):
    action: Action


class PendingOut(CamelModel):
    action: str
    execute_at: datetime
    remaining_seconds: int


class StatusOut(CamelModel):
    connected: bool
    last_seen_at: datetime | None
    hostname: str | None
    agent_version: str | None
    pending: PendingOut | None
    # Desconectado y con la hora ya vencida: lo más probable es que se haya ejecutado.
    probably_executed: bool
    server_time: datetime
