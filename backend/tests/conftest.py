from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Base
from app.core.security import hash_password
from app.main import create_app
from app.models import User

from .constants import AGENT_TOKEN, ORIGIN, PASSWORD, USERNAME
from .fakes import FakeAgent


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


@pytest.fixture
def fake_agent(client: TestClient) -> Iterator[FakeAgent]:
    with FakeAgent(client) as agent:
        yield agent
