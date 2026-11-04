import asyncio
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from ..core.database import SessionFactory, utcnow
from ..realtime.panel_broadcaster import PanelBroadcaster
from ..repositories.agent_state_repository import AgentStateRepository
from ..schemas.agent import AgentReportedState
from ..schemas.control import PendingOut, StatusOut
from ..schemas.realtime import StatusEvent


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

    def to_status(self, now: datetime | None = None) -> StatusOut:
        now = now or utcnow()
        pending = None
        if self.pending is not None:
            pending = PendingOut(
                action=self.pending.action,
                execute_at=self.pending.execute_at,
                remaining_seconds=self.pending.remaining_seconds(now),
            )
        return StatusOut(
            connected=self.connected,
            last_seen_at=self.last_seen_at,
            hostname=self.hostname,
            agent_version=self.agent_version,
            pending=pending,
            probably_executed=(
                not self.connected and self.pending is not None and self.pending.execute_at <= now
            ),
            server_time=now,
        )


def pending_from_report(state: AgentReportedState, now: datetime) -> PendingAction | None:
    """El agente informa segundos restantes; aquí se convierten en una hora de ejecución."""
    if state.pending is None:
        return None
    return PendingAction(
        action=state.pending.action.value,
        execute_at=now + timedelta(seconds=state.pending.remaining_seconds),
    )


class AgentStateService:
    """Último estado conocido del PC: en memoria, guardado en la BD y publicado al panel."""

    def __init__(self, sessions: SessionFactory, broadcaster: PanelBroadcaster) -> None:
        self._sessions = sessions
        self._broadcaster = broadcaster
        self._snapshot = AgentSnapshot()
        self._lock = asyncio.Lock()

    @property
    def snapshot(self) -> AgentSnapshot:
        return self._snapshot

    async def load(self) -> None:
        """Recupera el último estado guardado; al arrancar el backend el PC siempre está desconectado."""
        async with self._sessions() as db:
            row = await AgentStateRepository(db).get()
            if row is None:
                return
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

    async def update(self, **changes: Any) -> AgentSnapshot:
        # Se guarda antes de exponer el nuevo estado. El lock cubre también la publicación:
        # evita que dos cambios se pisen y que el panel los reciba en otro orden.
        async with self._lock:
            snapshot = replace(self._snapshot, **changes)
            async with self._sessions() as db:
                row = await AgentStateRepository(db).get_or_create()
                row.connected = snapshot.connected
                row.last_seen_at = snapshot.last_seen_at
                row.hostname = snapshot.hostname
                row.agent_version = snapshot.agent_version
                row.pending_action = snapshot.pending.action if snapshot.pending else None
                row.execute_at = snapshot.pending.execute_at if snapshot.pending else None
                await db.commit()
            self._snapshot = snapshot
            # publish no espera a nadie (encola y sigue), así que no retiene el lock.
            self._broadcaster.publish(StatusEvent(data=snapshot.to_status()))
        return snapshot
