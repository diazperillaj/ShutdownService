"""Eventos que recibe el panel por WebSocket."""

from typing import Literal

from .base import CamelModel
from .control import StatusOut
from .history import HistoryEntryOut


class StatusEvent(CamelModel):
    type: Literal["status"] = "status"
    data: StatusOut


class HistoryEvent(CamelModel):
    type: Literal["history"] = "history"
    data: HistoryEntryOut
