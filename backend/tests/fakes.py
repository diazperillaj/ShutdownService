import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from .constants import AGENT_TOKEN


def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("La condición no se cumplió a tiempo")


def agent_connected(client: TestClient) -> bool:
    return client.app.state.state_service.snapshot.connected


class FakeAgent:
    """Agente simulado que responde a los comandos desde un hilo aparte, como lo haría el PC."""

    def __init__(self, client: TestClient, responder: Callable[[dict], dict | None] | None = None):
        self._client = client
        self.responder = responder or self.default_responder
        self.pending: dict[str, Any] | None = None
        self.commands: "queue.Queue[dict]" = queue.Queue()
        self._thread: threading.Thread | None = None

    def state(self) -> dict[str, Any]:
        return {"pending": self.pending}

    def default_responder(self, command: dict) -> dict | None:
        action = command["action"]
        if action == "cancel" or not command.get("delaySeconds"):
            self.pending = None
        else:
            self.pending = {"action": action, "remainingSeconds": command["delaySeconds"]}
        return {"ok": True, "error": None}

    def __enter__(self) -> "FakeAgent":
        self._session = self._client.websocket_connect(
            "/ws/agent", headers={"authorization": f"Bearer {AGENT_TOKEN}"}
        )
        self.ws = self._session.__enter__()
        self.ws.send_json(
            {"type": "hello", "hostname": "PC-PRUEBA", "version": "1.0.0", "state": self.state()}
        )
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        wait_until(lambda: agent_connected(self._client))
        return self

    def _loop(self) -> None:
        while True:
            try:
                message = self.ws.receive_json()
            except Exception:
                return
            self.commands.put(message)
            reply = self.responder(message)
            if reply is not None:
                self.ws.send_json({"type": "ack", "id": message["id"], "state": self.state(), **reply})

    def send(self, message: dict) -> None:
        self.ws.send_json(message)

    def __exit__(self, *exc: object) -> None:
        # Cierra y espera a que el servidor registre la desconexión antes de que el cliente de
        # pruebas cancele la tarea; si no, la escritura en la base de datos queda a medias.
        self.ws.close(1000)
        wait_until(lambda: not agent_connected(self._client))
        self._session.__exit__(None, None, None)
        if self._thread is not None:
            self._thread.join(timeout=2)
