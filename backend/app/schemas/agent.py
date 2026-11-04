"""Protocolo JSON entre el backend y el servicio de Windows."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from ..models import Action
from .base import CamelModel


class AgentPending(CamelModel):
    action: Action
    remaining_seconds: int = Field(ge=0)


class AgentReportedState(CamelModel):
    pending: AgentPending | None = None


# --- Agente → servidor ---


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
agent_message_adapter: TypeAdapter[AgentMessage] = TypeAdapter(AgentMessage)


# --- Servidor → agente ---


class CommandMessage(CamelModel):
    type: Literal["command"] = "command"
    id: str
    action: str
    delay_seconds: int | None = None

    def to_json(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)
