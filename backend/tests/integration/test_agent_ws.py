import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.websockets import CLOSE_BAD_HELLO, CLOSE_UNAUTHORIZED

from ..constants import AGENT_TOKEN


def test_agent_with_wrong_token_is_rejected(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/agent", headers={"authorization": "Bearer malo"}):
            pass
    assert exc.value.code == CLOSE_UNAUTHORIZED


def test_agent_must_start_with_hello(client: TestClient):
    with client.websocket_connect(
        "/ws/agent", headers={"authorization": f"Bearer {AGENT_TOKEN}"}
    ) as ws:
        ws.send_json({"type": "state", "state": {"pending": None}})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == CLOSE_BAD_HELLO
    assert client.app.state.state_service.snapshot.connected is False
