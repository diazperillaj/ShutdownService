"""Reglas del diálogo con el PC: qué hacer con cada mensaje y cómo enviar comandos."""

import logging
from typing import Any

from pydantic import ValidationError

from ..core.database import utcnow
from ..core.errors import PcFailed, PcOffline, PcTimeout
from ..models import Result, Source
from ..realtime.agent_connection import (
    AgentConnection,
    AgentOfflineError,
    AgentSocket,
    AgentTimeoutError,
)
from ..schemas.agent import (
    AckMessage,
    AgentMessage,
    EventMessage,
    HelloMessage,
    StateMessage,
    agent_message_adapter,
)
from .agent_state_service import AgentSnapshot, AgentStateService, pending_from_report
from .history_service import HistoryService

log = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self, connection: AgentConnection, state: AgentStateService, history: HistoryService
    ) -> None:
        self._connection = connection
        self._state = state
        self._history = history

    @staticmethod
    def parse_message(raw: Any) -> AgentMessage:
        return agent_message_adapter.validate_python(raw)

    async def connect(self, ws: AgentSocket, hello: HelloMessage) -> None:
        await self._connection.attach(ws)
        now = utcnow()
        await self._state.update(
            connected=True,
            last_seen_at=now,
            hostname=hello.hostname,
            agent_version=hello.version,
            pending=pending_from_report(hello.state, now),
        )
        log.info("Agente conectado: %s (v%s)", hello.hostname, hello.version)

    async def disconnect(self, ws: AgentSocket) -> None:
        if self._connection.detach(ws):
            await self._state.update(connected=False)
            log.info("Agente desconectado")

    async def handle_message(self, ws: AgentSocket, raw: Any) -> None:
        if not self._connection.is_current(ws):
            return
        try:
            message = self.parse_message(raw)
        except ValidationError:
            log.warning("Mensaje del agente no válido: %.200r", raw)
            return

        now = utcnow()
        if isinstance(message, AckMessage):
            self._connection.resolve_ack(message)
        elif isinstance(message, StateMessage):
            await self._state.update(
                last_seen_at=now, pending=pending_from_report(message.state, now)
            )
        elif isinstance(message, EventMessage):
            result = Result.EXECUTED if message.event == "executing" else Result.DISCARDED
            await self._history.record(
                source=Source.AGENT,
                action=message.action.value,
                result=result,
                detail=message.reason,
            )
            await self._state.update(last_seen_at=now, pending=None)

    async def send_command(self, action: str, delay_seconds: int | None) -> AgentSnapshot:
        """Envía un comando, espera la confirmación y actualiza el estado con lo que informa el PC."""
        try:
            ack = await self._connection.send(action, delay_seconds)
        except AgentOfflineError:
            raise PcOffline() from None
        except AgentTimeoutError:
            raise PcTimeout() from None

        now = utcnow()
        snapshot = await self._state.update(
            last_seen_at=now, pending=pending_from_report(ack.state, now)
        )
        if not ack.ok:
            raise PcFailed(ack.error or "error desconocido")
        return snapshot
