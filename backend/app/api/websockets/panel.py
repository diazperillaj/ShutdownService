import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...core.database import utcnow
from ...schemas.realtime import StatusEvent
from ..deps import authenticate_websocket, get_broadcaster, get_control_service, get_settings
from . import CLOSE_FORBIDDEN, CLOSE_SESSION_EXPIRED, CLOSE_UNAUTHORIZED

router = APIRouter()


@router.websocket("/ws/panel")
async def panel_socket(ws: WebSocket) -> None:
    if ws.headers.get("origin") != get_settings(ws).public_origin:
        await ws.close(code=CLOSE_FORBIDDEN)
        return
    auth = await authenticate_websocket(ws)
    if auth is None:
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return

    await ws.accept()
    broadcaster = get_broadcaster(ws)
    queue = broadcaster.subscribe()
    # Detecta cuando el navegador cierra la conexión; el panel no envía mensajes.
    receiver = asyncio.create_task(_wait_for_disconnect(ws))
    try:
        await ws.send_json(StatusEvent(data=get_control_service(ws).status()).to_json())
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
        broadcaster.unsubscribe(queue)
        receiver.cancel()


async def _wait_for_disconnect(ws: WebSocket) -> None:
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
