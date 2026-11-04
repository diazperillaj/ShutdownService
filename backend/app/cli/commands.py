"""Tareas de administración.

    python -m app.cli create-user <usuario>
    python -m app.cli set-password <usuario>
    python -m app.cli gen-token
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Awaitable, Callable

from ..core.config import Settings
from ..core.database import create_db
from ..core.errors import AppError
from ..core.security import new_agent_token
from ..services.auth_service import AuthService


def _ask_password() -> str:
    password = getpass.getpass("Contraseña: ")
    if getpass.getpass("Repite la contraseña: ") != password:
        sys.exit("Las contraseñas no coinciden")
    return password


async def _with_auth_service(action: Callable[[AuthService], Awaitable[None]]) -> None:
    settings = Settings()
    engine, sessions = create_db(settings.database_url)
    try:
        async with sessions() as db:
            await action(AuthService(db, settings))
    except AppError as exc:
        sys.exit(exc.message)
    finally:
        await engine.dispose()


async def _create_user(username: str) -> None:
    async def action(auth: AuthService) -> None:
        await auth.ensure_can_create_user()  # antes de pedir la contraseña
        await auth.create_user(username, _ask_password())
        print(f"Usuario '{username}' creado")

    await _with_auth_service(action)


async def _set_password(username: str) -> None:
    async def action(auth: AuthService) -> None:
        await auth.ensure_user_exists(username)  # antes de pedir la contraseña
        await auth.reset_password(username, _ask_password())
        print(f"Contraseña de '{username}' actualizada; se cerraron sus sesiones")

    await _with_auth_service(action)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-user", help="Crea el único usuario del panel").add_argument("username")
    commands.add_parser("set-password", help="Cambia la contraseña y desbloquea").add_argument("username")
    commands.add_parser("gen-token", help="Genera un token aleatorio para AGENT_TOKEN")
    args = parser.parse_args()

    if args.command == "create-user":
        asyncio.run(_create_user(args.username))
    elif args.command == "set-password":
        asyncio.run(_set_password(args.username))
    elif args.command == "gen-token":
        print(new_agent_token())
