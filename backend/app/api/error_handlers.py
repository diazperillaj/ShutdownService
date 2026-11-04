from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..core.errors import AppError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
