"""Conexión con el servicio de Windows y estado compartido del PC.

El backend corre con un solo worker: la conexión del agente, las confirmaciones pendientes y los
suscriptores del panel viven en la memoria de este proceso.
"""

import asyncio
import logging
import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from fastapi import WebSocket
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import utcnow
from .models import ActionLog, AgentState, Result, Source
from .schemas import (
    AckMessage,
    AgentMessage,
    AgentReportedState,
    EventMessage,
    HelloMessage,
    StateMessage,
)

log = logging.getLogger(__name__)

_message_adapter: TypeAdapter[AgentMessage] = TypeAdapter(AgentMessage)
_SUBSCRIBER_QUEUE_SIZE = 100


class AgentOfflineError(Exception):
    pass


class AgentTimeoutError(Exception):
    pass


class AgentCommandError(Exception):
    pass


@dataclass(frozen=True)
class PendingAction:
    action: str
    execute_at: datetime

    def remaining_seconds(self, now: datetime) -> int:
        return max(0, math.ceil((self.execute_at - now).total_seconds()))


@dataclass(frozen=True)
class AgentSnapshot:
    connected: bool = False
    last_seen_at: datetime | None = None
    hostname: str | None = None
    agent_version: str | None = None
    pending: PendingAction | None = None

    def to_api(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        pending = None
        if self.pending is not None:
            pending = {
                "action": self.pending.action,
                "executeAt": self.pending.execute_at.isoformat(),
                "remainingSeconds": self.pending.remaining_seconds(now),
            }
        return {
            "connected": self.connected,
            "lastSeenAt": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "hostname": self.hostname,
            "agentVersion": self.agent_version,
            "pending": pending,
            # Desconectado y con la hora ya vencida: lo más probable es que se haya ejecutado.
            "probablyExecuted": (
                not self.connected
                and self.pending is not None
                and self.pending.execute_at <= now
            ),
            "serverTime": now.isoformat(),
        }


def history_entry(entry: ActionLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "createdAt": entry.created_at.isoformat(),
        "source": entry.source,
        "action": entry.action,
        "delaySeconds": entry.delay_seconds,
        "result": entry.result,
        "detail": entry.detail,
    }


def _pending_from_report(state: AgentReportedState, now: datetime) -> PendingAction | None:
    if state.pending is None:
        return None
    return PendingAction(
        action=state.pending.action.value,
        execute_at=now + timedelta(seconds=state.pending.remaining_seconds),
    )


class AgentHub:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], ack_timeout_seconds: float
    ) -> None:
        self._sessionmaker = sessionmaker
        self._ack_timeout = ack_timeout_seconds
        self._ws: WebSocket | None = None
        self._acks: dict[str, asyncio.Future[AckMessage]] = {}
        self._send_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._snapshot = AgentSnapshot()

    @property
    def snapshot(self) -> AgentSnapshot:
        return self._snapshot

    async def load(self) -> None:
        """Recupera el último estado conocido; al arrancar el agente siempre está desconectado."""
        async with self._sessionmaker() as db:
            row = await db.get(AgentState, 1)
            if row is not None:
                row.connected = False
                await db.commit()
                pending = None
                if row.pending_action and row.execute_at:
                    pending = PendingAction(row.pending_action, row.execute_at)
                self._snapshot = AgentSnapshot(
                    connected=False,
                    last_seen_at=row.last_seen_at,
                    hostname=row.hostname,
                    agent_version=row.agent_version,
                    pending=pending,
                )

    # --- Conexión del agente ---

    @staticmethod
    def parse_message(raw: Any) -> AgentMessage:
        return _message_adapter.validate_python(raw)

    async def attach(self, ws: WebSocket, hello: HelloMessage) -> None:
        previous, self._ws = self._ws, ws
        if previous is not None:
            log.warning("Nueva conexión del agente; se cierra la anterior")
            self._fail_pending_acks()
            try:
                await previous.close(code=4000)
            except Exception:  # la conexión anterior puede estar ya muerta
                pass
        now = utcnow()
        await self._update(
            connected=True,
            last_seen_at=now,
            hostname=hello.hostname,
            agent_version=hello.version,
            pending=_pending_from_report(hello.state, now),
        )
        log.info("Agente conectado: %s (v%s)", hello.hostname, hello.version)

    async def detach(self, ws: WebSocket) -> None:
        if self._ws is not ws:
            return
        self._ws = None
        self._fail_pending_acks()
        await self._update(connected=False)
        log.info("Agente desconectado")

    async def handle_message(self, ws: WebSocket, raw: Any) -> None:
        if ws is not self._ws:
            return
        try:
            message = self.parse_message(raw)
        except ValidationError:
            log.warning("Mensaje del agente no válido: %.200r", raw)
            return

        now = utcnow()
        if isinstance(message, AckMessage):
            future = self._acks.get(message.id)
            if future is not None and not future.done():
                future.set_result(message)
        elif isinstance(message, StateMessage):
            await self._update(last_seen_at=now, pending=_pending_from_report(message.state, now))
        elif isinstance(message, EventMessage):
            result = Result.EXECUTED if message.event == "executing" else Result.DISCARDED
            await self.log_action(
                source=Source.AGENT,
                action=message.action.value,
                result=result,
                detail=message.reason,
            )
            await self._update(last_seen_at=now, pending=None)

    async def send_command(self, action: str, delay_seconds: int | None = None) -> AgentSnapshot:
        """Envía un comando y espera la confirmación del agente."""
        ws = self._ws
        if ws is None:
            raise AgentOfflineError
        command_id = uuid.uuid4().hex
        future: asyncio.Future[AckMessage] = asyncio.get_running_loop().create_future()
        self._acks[command_id] = future
        payload: dict[str, Any] = {"type": "command", "id": command_id, "action": action}
        if delay_seconds is not None:
            payload["delaySeconds"] = delay_seconds
        try:
            async with self._send_lock:
                await ws.send_json(payload)
            ack = await asyncio.wait_for(future, self._ack_timeout)
        except TimeoutError as exc:
            raise AgentTimeoutError from exc
        except AgentOfflineError:
            raise
        except Exception as exc:  # el socket se cerró mientras se enviaba
            raise AgentOfflineError from exc
        finally:
            self._acks.pop(command_id, None)

        now = utcnow()
        await self._update(last_seen_at=now, pending=_pending_from_report(ack.state, now))
        if not ack.ok:
            raise AgentCommandError(ack.error or "Error desconocido en el PC")
        return self._snapshot

    def _fail_pending_acks(self) -> None:
        for future in self._acks.values():
            if not future.done():
                future.set_exception(AgentOfflineError())
        self._acks.clear()

    # --- Historial y estado ---

    async def log_action(
        self,
        *,
        source: Source,
        action: str,
        result: Result,
        delay_seconds: int | None = None,
        detail: str | None = None,
        user_id: int | None = None,
    ) -> None:
        async with self._sessionmaker() as db:
            entry = ActionLog(
                source=source.value,
                action=action,
                result=result.value,
                delay_seconds=delay_seconds,
                detail=detail,
                user_id=user_id,
            )
            db.add(entry)
            await db.commit()
        self._publish({"type": "history", "data": history_entry(entry)})

    async def _update(self, **changes: Any) -> None:
        # Se guarda antes de exponer el nuevo estado; el lock evita que dos cambios se pisen.
        async with self._update_lock:
            snap = replace(self._snapshot, **changes)
            async with self._sessionmaker() as db:
                row = await db.get(AgentState, 1)
                if row is None:
                    row = AgentState(id=1)
                    db.add(row)
                row.connected = snap.connected
                row.last_seen_at = snap.last_seen_at
                row.hostname = snap.hostname
                row.agent_version = snap.agent_version
                row.pending_action = snap.pending.action if snap.pending else None
                row.execute_at = snap.pending.execute_at if snap.pending else None
                await db.commit()
            self._snapshot = snap
        self._publish({"type": "status", "data": snap.to_api()})

    # --- Suscriptores del panel ---

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def _publish(self, event: dict[str, Any]) -> None:
        for queue in self._subscribers:
            if queue.full():  # un panel lento pierde el evento más antiguo
                queue.get_nowait()
            queue.put_nowait(event)
