import time
from collections import deque


class SlidingWindowLimiter:
    """Limita cuántas veces se usa una clave (por ejemplo, una IP) dentro de una ventana de tiempo."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> bool:
        """Registra un intento y devuelve False si la clave superó el límite."""
        now = time.monotonic()
        self._prune(now)
        hits = self._hits.setdefault(key, deque())
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]
