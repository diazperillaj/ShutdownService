import asyncio
import logging
import uuid
from typing import Any, Protocol

from ..schemas.agent import AckMessage, CommandMessage

log = logging.getLogger(__name__)


class AgentSocket(Protocol):
    """Lo único que se necesita del socket del PC (lo cumple el WebSocket de FastAPI)."""

    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000) -> None: ...


class AgentOfflineError(Exception):
    pass


class AgentTimeoutError(Exception):
    pass


class AgentConnection:
    """Socket del PC: envía comandos y empareja cada uno con su confirmación (ack)."""

    def __init__(self, ack_timeout_seconds: float) -> None:
        self._ack_timeout = ack_timeout_seconds
        self._ws: AgentSocket | None = None
        self._acks: dict[str, asyncio.Future[AckMessage]] = {}
        self._send_lock = asyncio.Lock()

    def is_current(self, ws: AgentSocket) -> bool:
        return ws is self._ws

    async def attach(self, ws: AgentSocket) -> None:
        """Registra el socket del PC; si había uno anterior, lo cierra."""
        previous, self._ws = self._ws, ws
        if previous is not None:
            log.warning("Nueva conexión del agente; se cierra la anterior")
            self._fail_pending_acks()
            try:
                await previous.close(code=4000)
            except Exception:  # la conexión anterior puede estar ya muerta
                pass

    def detach(self, ws: AgentSocket) -> bool:
        """Olvida el socket si es el actual. Devuelve False si ya había sido reemplazado."""
        if ws is not self._ws:
            return False
        self._ws = None
        self._fail_pending_acks()
        return True

    def resolve_ack(self, ack: AckMessage) -> None:
        future = self._acks.get(ack.id)
        if future is not None and not future.done():
            future.set_result(ack)

    async def send(self, action: str, delay_seconds: int | None) -> AckMessage:
        ws = self._ws
        if ws is None:
            raise AgentOfflineError
        command = CommandMessage(id=uuid.uuid4().hex, action=action, delay_seconds=delay_seconds)
        future: asyncio.Future[AckMessage] = asyncio.get_running_loop().create_future()
        self._acks[command.id] = future
        try:
            async with self._send_lock:
                await ws.send_json(command.to_json())
            return await asyncio.wait_for(future, self._ack_timeout)
        except TimeoutError as exc:
            raise AgentTimeoutError from exc
        except AgentOfflineError:
            raise
        except Exception as exc:  # el socket se cerró mientras se enviaba
            raise AgentOfflineError from exc
        finally:
            self._acks.pop(command.id, None)

    def _fail_pending_acks(self) -> None:
        for future in self._acks.values():
            if not future.done():
                future.set_exception(AgentOfflineError())
        self._acks.clear()
