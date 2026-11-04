import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # Argon2id con los parámetros recomendados por la librería
# Hash de relleno para que un usuario inexistente tarde lo mismo que una contraseña incorrecta.
_DUMMY_HASH = _hasher.hash("contraseña-de-relleno")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def burn_password_check(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_agent_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
