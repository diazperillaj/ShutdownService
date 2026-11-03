from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from .models import Action

MIN_DELAY_SECONDS = 60
MAX_DELAY_SECONDS = 24 * 60 * 60


class CamelModel(BaseModel):
    """Modelo que se serializa en camelCase para el frontend y el agente."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- API web ---


class LoginIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(CamelModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserOut(CamelModel):
    username: str


class ScheduleIn(CamelModel):
    action: Action
    delay_seconds: int | None = None
    # Hora concreta con zona horaria; el backend la convierte en segundos.
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


# --- Protocolo con el agente ---


class AgentPending(CamelModel):
    action: Action
    remaining_seconds: int = Field(ge=0)


class AgentReportedState(CamelModel):
    pending: AgentPending | None = None


class HelloMessage(CamelModel):
    type: Literal["hello"]
    hostname: str = Field(max_length=64)
    version: str = Field(max_length=32)
    state: AgentReportedState


class AckMessage(CamelModel):
    type: Literal["ack"]
    id: str = Field(max_length=64)
    ok: bool
    error: str | None = Field(default=None, max_length=256)
    state: AgentReportedState


class StateMessage(CamelModel):
    type: Literal["state"]
    state: AgentReportedState


class EventMessage(CamelModel):
    type: Literal["event"]
    event: Literal["executing", "discarded"]
    action: Action
    reason: str | None = Field(default=None, max_length=64)


AgentMessage = Annotated[
    HelloMessage | AckMessage | StateMessage | EventMessage, Field(discriminator="type")
]
