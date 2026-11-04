from datetime import UTC, datetime, timedelta

from app.models import Action
from app.schemas.agent import AgentPending, AgentReportedState
from app.services.agent_state_service import AgentSnapshot, PendingAction, pending_from_report

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def test_pending_from_report_converts_seconds_into_time():
    state = AgentReportedState(pending=AgentPending(action=Action.SHUTDOWN, remaining_seconds=90))

    pending = pending_from_report(state, NOW)

    assert pending == PendingAction("shutdown", NOW + timedelta(seconds=90))
    assert pending_from_report(AgentReportedState(), NOW) is None


def test_status_shows_remaining_time():
    snapshot = AgentSnapshot(connected=True, pending=PendingAction("restart", NOW + timedelta(minutes=5)))

    status = snapshot.to_status(NOW)

    assert status.pending.remaining_seconds == 300
    assert status.probably_executed is False


def test_disconnected_with_past_time_is_probably_executed():
    snapshot = AgentSnapshot(connected=False, pending=PendingAction("shutdown", NOW - timedelta(seconds=1)))

    status = snapshot.to_status(NOW)

    assert status.probably_executed is True
    assert status.pending.remaining_seconds == 0


def test_status_serializes_in_camel_case():
    payload = AgentSnapshot().to_status(NOW).to_json()

    assert set(payload) == {
        "connected",
        "lastSeenAt",
        "hostname",
        "agentVersion",
        "pending",
        "probablyExecuted",
        "serverTime",
    }
