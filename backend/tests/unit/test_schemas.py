from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Action
from app.schemas.agent import AckMessage, CommandMessage, agent_message_adapter
from app.schemas.control import ScheduleIn


def test_schedule_accepts_delay_or_time_but_not_both():
    assert ScheduleIn.model_validate({"action": "shutdown", "delaySeconds": 600}).delay_seconds == 600
    at = datetime(2030, 1, 1, tzinfo=UTC)
    assert ScheduleIn.model_validate({"action": "restart", "at": at.isoformat()}).at == at

    with pytest.raises(ValidationError):
        ScheduleIn.model_validate({"action": "shutdown"})
    with pytest.raises(ValidationError):
        ScheduleIn.model_validate({"action": "shutdown", "delaySeconds": 60, "at": at.isoformat()})


def test_schedule_rejects_time_without_timezone():
    with pytest.raises(ValidationError):
        ScheduleIn.model_validate({"action": "shutdown", "at": "2030-01-01T10:00:00"})


def test_agent_messages_are_parsed_by_type():
    ack = agent_message_adapter.validate_python(
        {
            "type": "ack",
            "id": "abc",
            "ok": True,
            "state": {"pending": {"action": "sleep", "remainingSeconds": 30}},
        }
    )

    assert isinstance(ack, AckMessage)
    assert ack.state.pending.action is Action.SLEEP
    assert ack.state.pending.remaining_seconds == 30

    with pytest.raises(ValidationError):
        agent_message_adapter.validate_python({"type": "desconocido"})


def test_command_message_is_camel_case_without_nulls():
    assert CommandMessage(id="1", action="cancel").to_json() == {
        "type": "command",
        "id": "1",
        "action": "cancel",
    }
    assert CommandMessage(id="2", action="shutdown", delay_seconds=60).to_json()["delaySeconds"] == 60
