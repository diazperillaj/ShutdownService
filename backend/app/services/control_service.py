"""Operaciones sobre el PC, compartidas por la API web y la skill de Alexa."""

from dataclasses import dataclass
from datetime import datetime

from ..core.constants import MAX_DELAY_SECONDS, MIN_DELAY_SECONDS
from ..core.database import utcnow
from ..core.errors import InvalidRequest, NothingScheduled, PcFailed, PcOffline, PcTimeout
from ..models import PROGRAMMABLE_ACTIONS, Action, Result, Source
from ..models.enums import CANCEL_COMMAND
from ..schemas.control import StatusOut
from .agent_service import AgentService
from .agent_state_service import AgentSnapshot, AgentStateService
from .history_service import HistoryService


@dataclass(frozen=True)
class CancelResult:
    snapshot: AgentSnapshot
    had_pending: bool


def _validate_delay(delay_seconds: int) -> None:
    if not MIN_DELAY_SECONDS <= delay_seconds <= MAX_DELAY_SECONDS:
        raise InvalidRequest("El tiempo debe estar entre 1 minuto y 24 horas")


class ControlService:
    def __init__(
        self, agent: AgentService, state: AgentStateService, history: HistoryService
    ) -> None:
        self._agent = agent
        self._state = state
        self._history = history

    def status(self) -> StatusOut:
        return self._state.snapshot.to_status()

    async def schedule(
        self, action: Action, delay_seconds: int, *, source: Source, user_id: int | None = None
    ) -> AgentSnapshot:
        if action not in PROGRAMMABLE_ACTIONS:
            raise InvalidRequest("Esta acción solo puede ejecutarse de inmediato")
        _validate_delay(delay_seconds)
        return await self._run(action.value, delay_seconds, source=source, user_id=user_id)

    async def schedule_at(
        self, action: Action, at: datetime, *, source: Source, user_id: int | None = None
    ) -> AgentSnapshot:
        delay = round((at - utcnow()).total_seconds())
        return await self.schedule(action, delay, source=source, user_id=user_id)

    async def extend(
        self, seconds: int, *, source: Source, user_id: int | None = None
    ) -> AgentSnapshot:
        snapshot = self._state.snapshot
        if not snapshot.connected:
            raise PcOffline()
        if snapshot.pending is None:
            raise NothingScheduled()
        new_delay = snapshot.pending.remaining_seconds(utcnow()) + seconds
        if new_delay > MAX_DELAY_SECONDS:
            raise InvalidRequest("El tiempo total no puede superar 24 horas")
        return await self._run(
            snapshot.pending.action,
            new_delay,
            source=source,
            user_id=user_id,
            detail=f"Extendido {seconds // 60} min",
        )

    async def cancel(self, *, source: Source, user_id: int | None = None) -> CancelResult:
        had_pending = self._state.snapshot.pending is not None
        snapshot = await self._run(CANCEL_COMMAND, None, source=source, user_id=user_id)
        return CancelResult(snapshot=snapshot, had_pending=had_pending)

    async def run_now(
        self, action: Action, *, source: Source, user_id: int | None = None
    ) -> AgentSnapshot:
        return await self._run(action.value, 0, source=source, user_id=user_id)

    async def _run(
        self,
        command: str,
        delay_seconds: int | None,
        *,
        source: Source,
        user_id: int | None,
        detail: str | None = None,
    ) -> AgentSnapshot:
        """Envía el comando y deja constancia en el historial, haya salido bien o mal."""

        async def record(result: Result, error_detail: str | None = None) -> None:
            await self._history.record(
                source=source,
                action=command,
                result=result,
                delay_seconds=delay_seconds,
                detail=error_detail or detail,
                user_id=user_id,
            )

        try:
            snapshot = await self._agent.send_command(command, delay_seconds)
        except PcOffline:
            await record(Result.OFFLINE)
            raise
        except PcTimeout:
            await record(Result.TIMEOUT)
            raise
        except PcFailed as exc:
            await record(Result.ERROR, exc.reason)
            raise
        await record(Result.OK)
        return snapshot
