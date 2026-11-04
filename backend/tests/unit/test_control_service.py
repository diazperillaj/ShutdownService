import asyncio
from datetime import timedelta

import pytest

from app.core.database import utcnow
from app.core.errors import InvalidRequest, NothingScheduled, PcFailed, PcOffline
from app.models import Action, Result, Source
from app.services.agent_state_service import AgentSnapshot, PendingAction
from app.services.control_service import ControlService


class StubState:
    def __init__(self, snapshot: AgentSnapshot) -> None:
        self.snapshot = snapshot


class StubAgent:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[tuple[str, int | None]] = []
        self.error = error

    async def send_command(self, action: str, delay_seconds: int | None) -> AgentSnapshot:
        self.sent.append((action, delay_seconds))
        if self.error is not None:
            raise self.error
        return AgentSnapshot(connected=True)


class StubHistory:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **entry) -> None:
        self.records.append(entry)


def make_service(snapshot: AgentSnapshot | None = None, error: Exception | None = None):
    agent, history = StubAgent(error), StubHistory()
    service = ControlService(agent, StubState(snapshot or AgentSnapshot(connected=True)), history)
    return service, agent, history


def test_schedule_sends_command_and_records_ok():
    service, agent, history = make_service()

    asyncio.run(service.schedule(Action.SHUTDOWN, 600, source=Source.ALEXA, user_id=None))

    assert agent.sent == [("shutdown", 600)]
    assert history.records[0]["result"] is Result.OK
    assert history.records[0]["source"] is Source.ALEXA


@pytest.mark.parametrize("delay", [59, 24 * 3600 + 1])
def test_schedule_rejects_delay_out_of_range(delay):
    service, agent, _ = make_service()

    with pytest.raises(InvalidRequest):
        asyncio.run(service.schedule(Action.SHUTDOWN, delay, source=Source.WEB))
    assert agent.sent == []


def test_lock_cannot_be_scheduled():
    service, agent, _ = make_service()

    with pytest.raises(InvalidRequest):
        asyncio.run(service.schedule(Action.LOCK, 600, source=Source.WEB))
    assert agent.sent == []


def test_extend_requires_pending_and_respects_limit():
    service, _, _ = make_service(AgentSnapshot(connected=True))
    with pytest.raises(NothingScheduled):
        asyncio.run(service.extend(900, source=Source.WEB))

    near_limit = PendingAction("shutdown", utcnow() + timedelta(hours=23, minutes=55))
    service, agent, _ = make_service(AgentSnapshot(connected=True, pending=near_limit))
    with pytest.raises(InvalidRequest):
        asyncio.run(service.extend(900, source=Source.WEB))
    assert agent.sent == []


def test_extend_while_offline():
    pending = PendingAction("shutdown", utcnow() + timedelta(minutes=10))
    service, _, _ = make_service(AgentSnapshot(connected=False, pending=pending))

    with pytest.raises(PcOffline):
        asyncio.run(service.extend(900, source=Source.WEB))


def test_cancel_reports_whether_something_was_pending():
    pending = PendingAction("sleep", utcnow() + timedelta(minutes=10))
    service, agent, _ = make_service(AgentSnapshot(connected=True, pending=pending))

    result = asyncio.run(service.cancel(source=Source.ALEXA))

    assert result.had_pending is True
    assert agent.sent == [("cancel", None)]


@pytest.mark.parametrize(
    ("error", "result", "detail"),
    [
        (PcOffline(), Result.OFFLINE, None),
        (PcFailed("sin permisos"), Result.ERROR, "sin permisos"),
    ],
)
def test_failures_are_recorded_and_reraised(error, result, detail):
    service, _, history = make_service(error=error)

    with pytest.raises(type(error)):
        asyncio.run(service.run_now(Action.RESTART, source=Source.WEB))
    assert history.records[0]["result"] is result
    assert history.records[0]["detail"] == detail
