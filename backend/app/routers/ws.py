import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..agent_hub import AgentHub
from ..auth import SESSION_COOKIE, resolve_session
from ..config import Settings
from ..db import utcnow
from ..schemas import HelloMessage
from ..security import secrets_equal

log = logging.getLogger(__name__)
router = APIRouter()

# Códigos de cierre propios (rango 4000-4999 reservado para aplicaciones).
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_BAD_HELLO = 4400
CLOSE_SESSION_EXPIRED = 4440

_HELLO_TIMEOUT_SECONDS = 10


@router.websocket("/ws/agent")
async def agent_socket(ws: WebSocket) -> None:
    settings: Settings = ws.app.state.settings
    hub: AgentHub = ws.app.state.hub

    expected = f"Bearer {settings.agent_token.get_secret_value()}"
    if not secrets_equal(ws.headers.get("authorization", ""), expected):
        log.warning("Conexión de agente rechazada desde %s", ws.client.host if ws.client else "?")
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return

    await ws.accept()
    try:
        raw = await asyncio.wait_for(ws.receive_json(), _HELLO_TIMEOUT_SECONDS)
        hello = hub.parse_message(raw)
        if not isinstance(hello, HelloMessage):
            raise ValueError("El primer mensaje debe ser hello")
    except (TimeoutError, ValidationError, ValueError):
        await ws.close(code=CLOSE_BAD_HELLO)
        return
    except WebSocketDisconnect:
        return

    await hub.attach(ws, hello)
    try:
        while True:
            text = await ws.receive_text()
            try:
                raw = json.loads(text)
            except ValueError:
                log.warning("El agente envió JSON no válido")
                continue
            await hub.handle_message(ws, raw)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.detach(ws)


@router.websocket("/ws/panel")
async def panel_socket(ws: WebSocket) -> None:
    settings: Settings = ws.app.state.settings
    hub: AgentHub = ws.app.state.hub

    if ws.headers.get("origin") != settings.public_origin:
        await ws.close(code=CLOSE_FORBIDDEN)
        return
    token = ws.cookies.get(SESSION_COOKIE)
    auth = None
    if token:
        async with ws.app.state.sessionmaker() as db:
            auth = await resolve_session(db, token)
    if auth is None:
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return

    await ws.accept()
    queue = hub.subscribe()
    # Detecta cuando el navegador cierra la conexión; el panel no envía mensajes.
    receiver = asyncio.create_task(_wait_for_disconnect(ws))
    try:
        await ws.send_json({"type": "status", "data": hub.snapshot.to_api()})
        while True:
            remaining = (auth.session.expires_at - utcnow()).total_seconds()
            if remaining <= 0:
                await ws.close(code=CLOSE_SESSION_EXPIRED)
                break
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {getter, receiver}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            if getter not in done:
                getter.cancel()
                if receiver in done:
                    break
                continue  # venció la sesión; se cierra en la siguiente vuelta
            await ws.send_json(getter.result())
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
        receiver.cancel()


async def _wait_for_disconnect(ws: WebSocket) -> None:
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
