import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth import SESSION_COOKIE

from .conftest import FakeAgent, wait_until


def test_panel_requires_session(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/panel"):
            pass
    assert exc.value.code == 4401


def test_panel_rejects_foreign_origin(logged_in: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with logged_in.websocket_connect(
            "/ws/panel",
            headers={"origin": "https://malicioso.example", **_session_header(logged_in)},
        ):
            pass
    assert exc.value.code == 4403


def _session_header(client: TestClient) -> dict[str, str]:
    # El cliente de pruebas no adjunta cookies Secure en wss://; los navegadores sí lo hacen.
    return {"cookie": f"{SESSION_COOKIE}={client.cookies.get(SESSION_COOKIE)}"}


def test_panel_receives_live_updates(logged_in: TestClient):
    with logged_in.websocket_connect("/ws/panel", headers=_session_header(logged_in)) as panel:
        initial = panel.receive_json()
        assert initial["type"] == "status"
        assert initial["data"]["connected"] is False

        with FakeAgent(logged_in) as agent:
            connected = panel.receive_json()
            assert connected["type"] == "status"
            assert connected["data"]["connected"] is True

            logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 600})
            agent.commands.get(timeout=1)

            events = [panel.receive_json(), panel.receive_json()]
            types = {event["type"] for event in events}
            assert types == {"status", "history"}
            status = next(e for e in events if e["type"] == "status")
            assert status["data"]["pending"]["action"] == "shutdown"

        wait_until(lambda: not logged_in.app.state.hub.snapshot.connected)
