from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from ..fakes import FakeAgent, agent_connected, wait_until


def test_status_when_agent_never_connected(logged_in: TestClient):
    status = logged_in.get("/api/status").json()

    assert status["connected"] is False
    assert status["pending"] is None
    assert status["probablyExecuted"] is False


def test_agent_connects_and_reports_hostname(logged_in: TestClient, fake_agent: FakeAgent):
    status = logged_in.get("/api/status").json()

    assert status["connected"] is True
    assert status["hostname"] == "PC-PRUEBA"
    assert status["agentVersion"] == "1.0.0"


def test_schedule_sends_command_and_returns_state(logged_in: TestClient, fake_agent: FakeAgent):
    response = logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 1800})

    assert response.status_code == 200, response.text
    command = fake_agent.commands.get(timeout=1)
    assert command["type"] == "command"
    assert command["action"] == "shutdown"
    assert command["delaySeconds"] == 1800
    pending = response.json()["pending"]
    assert pending["action"] == "shutdown"
    assert 1795 <= pending["remainingSeconds"] <= 1800


def test_schedule_at_specific_time(logged_in: TestClient, fake_agent: FakeAgent):
    at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()

    response = logged_in.post("/api/schedule", json={"action": "restart", "at": at})

    assert response.status_code == 200, response.text
    assert 7190 <= fake_agent.commands.get(timeout=1)["delaySeconds"] <= 7200


def test_schedule_validation(logged_in: TestClient, fake_agent: FakeAgent):
    too_short = logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 30})
    too_long = logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 90000})
    lock = logged_in.post("/api/schedule", json={"action": "lock", "delaySeconds": 600})
    both = logged_in.post(
        "/api/schedule",
        json={"action": "shutdown", "delaySeconds": 600, "at": datetime.now(UTC).isoformat()},
    )
    unknown = logged_in.post("/api/schedule", json={"action": "explotar", "delaySeconds": 600})

    assert too_short.status_code == 422
    assert too_long.status_code == 422
    assert lock.status_code == 422
    assert both.status_code == 422
    assert unknown.status_code == 422
    assert fake_agent.commands.empty()


def test_mutations_require_same_origin(logged_in: TestClient, fake_agent: FakeAgent):
    response = logged_in.post(
        "/api/schedule",
        json={"action": "shutdown", "delaySeconds": 600},
        headers={"origin": "https://malicioso.example"},
    )
    assert response.status_code == 403
    assert fake_agent.commands.empty()


def test_extend_adds_time_to_pending_action(logged_in: TestClient, fake_agent: FakeAgent):
    logged_in.post("/api/schedule", json={"action": "hibernate", "delaySeconds": 600})
    fake_agent.commands.get(timeout=1)

    response = logged_in.post("/api/schedule/extend", json={"seconds": 900})

    assert response.status_code == 200, response.text
    command = fake_agent.commands.get(timeout=1)
    assert command["action"] == "hibernate"
    assert 1495 <= command["delaySeconds"] <= 1500


def test_extend_without_pending_action(logged_in: TestClient, fake_agent: FakeAgent):
    response = logged_in.post("/api/schedule/extend", json={"seconds": 900})
    assert response.status_code == 409


def test_cancel_clears_pending(logged_in: TestClient, fake_agent: FakeAgent):
    logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 600})

    response = logged_in.delete("/api/schedule")

    assert response.status_code == 200
    assert response.json()["pending"] is None


def test_run_now_sends_zero_delay(logged_in: TestClient, fake_agent: FakeAgent):
    response = logged_in.post("/api/actions/now", json={"action": "lock"})

    assert response.status_code == 200, response.text
    command = fake_agent.commands.get(timeout=1)
    assert command["action"] == "lock"
    assert command["delaySeconds"] == 0


def test_commands_rejected_when_pc_offline(logged_in: TestClient):
    response = logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 600})

    assert response.status_code == 409
    assert response.json()["detail"] == "El PC no está conectado"
    assert logged_in.get("/api/history").json()[0]["result"] == "offline"


def test_agent_timeout(logged_in: TestClient):
    with FakeAgent(logged_in, responder=lambda command: None):
        response = logged_in.post("/api/actions/now", json={"action": "sleep"})

    assert response.status_code == 504
    assert logged_in.get("/api/history").json()[0]["result"] == "timeout"


def test_agent_error_is_reported(logged_in: TestClient):
    def fail(command: dict) -> dict:
        return {"ok": False, "error": "La hibernación está desactivada"}

    with FakeAgent(logged_in, responder=fail):
        response = logged_in.post("/api/actions/now", json={"action": "hibernate"})

    assert response.status_code == 502
    assert "La hibernación está desactivada" in response.json()["detail"]
    latest = logged_in.get("/api/history").json()[0]
    assert (latest["result"], latest["detail"]) == ("error", "La hibernación está desactivada")


def test_history_records_actions_with_source(logged_in: TestClient, fake_agent: FakeAgent):
    logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 600})
    logged_in.delete("/api/schedule")

    history = logged_in.get("/api/history").json()

    assert [(h["action"], h["source"], h["result"]) for h in history] == [
        ("cancel", "web", "ok"),
        ("shutdown", "web", "ok"),
    ]


def test_agent_events_are_logged_and_clear_pending(logged_in: TestClient, fake_agent: FakeAgent):
    logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 600})

    fake_agent.send({"type": "event", "event": "discarded", "action": "shutdown", "reason": "resume"})
    wait_until(lambda: logged_in.get("/api/status").json()["pending"] is None)

    latest = logged_in.get("/api/history").json()[0]
    assert (latest["source"], latest["result"], latest["detail"]) == ("agent", "discarded", "resume")


def test_disconnect_keeps_last_known_state(logged_in: TestClient):
    with FakeAgent(logged_in) as agent:
        logged_in.post("/api/schedule", json={"action": "shutdown", "delaySeconds": 600})
        agent.commands.get(timeout=1)

    assert not agent_connected(logged_in)
    status = logged_in.get("/api/status").json()
    assert status["connected"] is False
    assert status["pending"]["action"] == "shutdown"
    assert status["probablyExecuted"] is False
