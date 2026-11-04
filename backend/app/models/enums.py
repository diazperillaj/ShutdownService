from enum import StrEnum


class Action(StrEnum):
    SHUTDOWN = "shutdown"
    RESTART = "restart"
    SLEEP = "sleep"
    HIBERNATE = "hibernate"
    LOCK = "lock"


# Acciones que admiten temporizador; bloquear solo es inmediata.
PROGRAMMABLE_ACTIONS = frozenset(Action) - {Action.LOCK}

# Comando del protocolo para anular la acción programada (no es una acción del PC).
CANCEL_COMMAND = "cancel"


class Source(StrEnum):
    WEB = "web"
    ALEXA = "alexa"
    AGENT = "agent"


class Result(StrEnum):
    OK = "ok"
    ERROR = "error"
    OFFLINE = "offline"
    TIMEOUT = "timeout"
    EXECUTED = "executed"
    DISCARDED = "discarded"
