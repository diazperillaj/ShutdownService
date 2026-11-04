import queue
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base
from app.main import create_app
from app.models import User
from app.security import hash_password

ORIGIN = "https://panel.test"
AGENT_TOKEN = "t" * 48
USERNAME = "admin"
PASSWORD = "una-clave-segura"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(username=USERNAME, password_hash=hash_password(PASSWORD)))
        db.commit()
    engine.dispose()
    return path


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{db_path}",
        agent_token=AGENT_TOKEN,
        public_origin=ORIGIN,
        ack_timeout_seconds=1.0,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver", headers={"origin": ORIGIN}) as c:
        yield c


@pytest.fixture
def logged_in(client: TestClient) -> TestClient:
    response = client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


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
        if action == "cancel":
            self.pending = None
        elif command.get("delaySeconds", 0) > 0:
            self.pending = {"action": action, "remainingSeconds": command["delaySeconds"]}
        else:
            self.pending = None
        return {"ok": True, "error": None}

    def __enter__(self) -> "FakeAgent":
        self._cm = self._client.websocket_connect(
            "/ws/agent", headers={"authorization": f"Bearer {AGENT_TOKEN}"}
        )
        self.ws = self._cm.__enter__()
        self.ws.send_json(
            {"type": "hello", "hostname": "PC-PRUEBA", "version": "1.0.0", "state": self.state()}
        )
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
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
        wait_until(lambda: not self._client.app.state.hub.snapshot.connected)
        self._cm.__exit__(None, None, None)
        if self._thread is not None:
            self._thread.join(timeout=2)


@pytest.fixture
def fake_agent(client: TestClient) -> Iterator[FakeAgent]:
    with FakeAgent(client) as agent:
        wait_until(lambda: client.app.state.hub.snapshot.connected)
        yield agent


def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("La condición no se cumplió a tiempo")
