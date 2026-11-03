"""Operaciones sobre el PC, compartidas por la API web y la skill de Alexa."""

from dataclasses import dataclass

from .agent_hub import (
    AgentCommandError,
    AgentHub,
    AgentOfflineError,
    AgentSnapshot,
    AgentTimeoutError,
)
from .db import utcnow
from .models import PROGRAMMABLE_ACTIONS, Action, Result, Source
from .schemas import MAX_DELAY_SECONDS, MIN_DELAY_SECONDS

CANCEL = "cancel"


class ControlError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRequest(ControlError):
    status_code = 422


class PcOffline(ControlError):
    status_code = 409


class NothingScheduled(ControlError):
    status_code = 409


class PcTimeout(ControlError):
    status_code = 504


class PcFailed(ControlError):
    status_code = 502


@dataclass(frozen=True)
class CancelResult:
    snapshot: AgentSnapshot
    had_pending: bool


def _validate_delay(delay_seconds: int) -> None:
    if not MIN_DELAY_SECONDS <= delay_seconds <= MAX_DELAY_SECONDS:
        raise InvalidRequest("El tiempo debe estar entre 1 minuto y 24 horas")


class ControlService:
    def __init__(self, hub: AgentHub) -> None:
        self._hub = hub

    async def schedule(
        self, action: Action, delay_seconds: int, *, source: Source, user_id: int | None = None
    ) -> AgentSnapshot:
        if action not in PROGRAMMABLE_ACTIONS:
            raise InvalidRequest("Esta acción solo puede ejecutarse de inmediato")
        _validate_delay(delay_seconds)
        return await self._run(
            action.value, delay_seconds, source=source, user_id=user_id, log_action=action.value
        )

    async def extend(
        self, seconds: int, *, source: Source, user_id: int | None = None
    ) -> AgentSnapshot:
        snapshot = self._hub.snapshot
        if not snapshot.connected:
            raise PcOffline("El PC no está conectado")
        if snapshot.pending is None:
            raise NothingScheduled("No hay ninguna acción programada")
        new_delay = snapshot.pending.remaining_seconds(utcnow()) + seconds
        if new_delay > MAX_DELAY_SECONDS:
            raise InvalidRequest("El tiempo total no puede superar 24 horas")
        return await self._run(
            snapshot.pending.action,
            new_delay,
            source=source,
            user_id=user_id,
            log_action=snapshot.pending.action,
            detail=f"Extendido {seconds // 60} min",
        )

    async def cancel(self, *, source: Source, user_id: int | None = None) -> CancelResult:
        had_pending = self._hub.snapshot.pending is not None
        snapshot = await self._run(
            CANCEL, None, source=source, user_id=user_id, log_action=CANCEL
        )
        return CancelResult(snapshot=snapshot, had_pending=had_pending)

    async def run_now(
        self, action: Action, *, source: Source, user_id: int | None = None
    ) -> AgentSnapshot:
        return await self._run(action.value, 0, source=source, user_id=user_id, log_action=action.value)

    async def _run(
        self,
        command: str,
        delay_seconds: int | None,
        *,
        source: Source,
        user_id: int | None,
        log_action: str,
        detail: str | None = None,
    ) -> AgentSnapshot:
        async def record(result: Result, error_detail: str | None = None) -> None:
            await self._hub.log_action(
                source=source,
                action=log_action,
                result=result,
                delay_seconds=delay_seconds,
                detail=error_detail or detail,
                user_id=user_id,
            )

        try:
            snapshot = await self._hub.send_command(command, delay_seconds)
        except AgentOfflineError:
            await record(Result.OFFLINE)
            raise PcOffline("El PC no está conectado") from None
        except AgentTimeoutError:
            await record(Result.TIMEOUT)
            raise PcTimeout("El PC no respondió a tiempo") from None
        except AgentCommandError as exc:
            await record(Result.ERROR, str(exc))
            raise PcFailed(f"El PC no pudo ejecutar la acción: {exc}") from None
        await record(Result.OK)
        return snapshot
