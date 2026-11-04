import asyncio
from typing import Any

from ..schemas.base import CamelModel

_QUEUE_SIZE = 100


class PanelBroadcaster:
    """Reparte los eventos (estado e historial) a todos los paneles conectados."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: CamelModel) -> None:
        payload = event.to_json()
        for queue in self._subscribers:
            if queue.full():  # un panel lento pierde el evento más antiguo
                queue.get_nowait()
            queue.put_nowait(payload)
