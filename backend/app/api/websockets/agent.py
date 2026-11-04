import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ...core.security import secrets_equal
from ...schemas.agent import HelloMessage
from ..deps import get_agent_service, get_settings
from . import CLOSE_BAD_HELLO, CLOSE_UNAUTHORIZED

log = logging.getLogger(__name__)
router = APIRouter()

_HELLO_TIMEOUT_SECONDS = 10


@router.websocket("/ws/agent")
async def agent_socket(ws: WebSocket) -> None:
    settings = get_settings(ws)
    agent_service = get_agent_service(ws)

    expected = f"Bearer {settings.agent_token.get_secret_value()}"
    if not secrets_equal(ws.headers.get("authorization", ""), expected):
        log.warning("Conexión de agente rechazada desde %s", ws.client.host if ws.client else "?")
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return

    await ws.accept()
    try:
        raw = await asyncio.wait_for(ws.receive_json(), _HELLO_TIMEOUT_SECONDS)
        hello = agent_service.parse_message(raw)
        if not isinstance(hello, HelloMessage):
            raise ValueError("El primer mensaje debe ser hello")
    except (TimeoutError, ValidationError, ValueError):
        await ws.close(code=CLOSE_BAD_HELLO)
        return
    except WebSocketDisconnect:
        return

    await agent_service.connect(ws, hello)
    try:
        while True:
            text = await ws.receive_text()
            try:
                raw = json.loads(text)
            except ValueError:
                log.warning("El agente envió JSON no válido")
                continue
            await agent_service.handle_message(ws, raw)
    except WebSocketDisconnect:
        pass
    finally:
        await agent_service.disconnect(ws)
