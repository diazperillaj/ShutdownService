"""Tareas de administración.

    python -m app.cli create-user <usuario>
    python -m app.cli set-password <usuario>
    python -m app.cli gen-token
"""

import argparse
import asyncio
import getpass
import secrets
import sys

from sqlalchemy import func, select

from .config import Settings
from .db import create_db
from .models import User, UserSession
from .security import MIN_PASSWORD_LENGTH, hash_password


def _ask_password() -> str:
    password = getpass.getpass("Contraseña: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    if getpass.getpass("Repite la contraseña: ") != password:
        sys.exit("Las contraseñas no coinciden")
    return password


async def _create_user(username: str) -> None:
    engine, sessionmaker = create_db(Settings().database_url)
    try:
        async with sessionmaker() as db:
            if await db.scalar(select(func.count()).select_from(User)):
                sys.exit("Ya existe un usuario. Usa set-password para cambiar su contraseña")
            db.add(User(username=username, password_hash=hash_password(_ask_password())))
            await db.commit()
        print(f"Usuario '{username}' creado")
    finally:
        await engine.dispose()


async def _set_password(username: str) -> None:
    engine, sessionmaker = create_db(Settings().database_url)
    try:
        async with sessionmaker() as db:
            user = await db.scalar(select(User).where(User.username == username))
            if user is None:
                sys.exit(f"No existe el usuario '{username}'")
            user.password_hash = hash_password(_ask_password())
            user.failed_attempts = 0
            user.locked_until = None
            # Cierra todas las sesiones abiertas.
            for session in await db.scalars(select(UserSession).where(UserSession.user_id == user.id)):
                await db.delete(session)
            await db.commit()
        print(f"Contraseña de '{username}' actualizada; se cerraron sus sesiones")
    finally:
        await engine.dispose()


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
        print(secrets.token_urlsafe(48))


if __name__ == "__main__":
    main()
