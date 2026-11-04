"""Errores de la aplicación. Cada uno indica con qué código HTTP se responde."""


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRequest(AppError):
    status_code = 422


class NotAuthenticated(AppError):
    status_code = 401


class InvalidCredentials(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class TooManyAttempts(AppError):
    status_code = 429


class PcOffline(Conflict):
    def __init__(self, message: str = "El PC no está conectado") -> None:
        super().__init__(message)


class NothingScheduled(Conflict):
    def __init__(self, message: str = "No hay ninguna acción programada") -> None:
        super().__init__(message)


class PcFailed(AppError):
    status_code = 502

    def __init__(self, reason: str) -> None:
        super().__init__(f"El PC no pudo ejecutar la acción: {reason}")
        self.reason = reason


class PcTimeout(AppError):
    status_code = 504

    def __init__(self, message: str = "El PC no respondió a tiempo") -> None:
        super().__init__(message)
