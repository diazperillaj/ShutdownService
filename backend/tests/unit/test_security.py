from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import (
    hash_password,
    hash_token,
    new_session_token,
    secrets_equal,
    verify_password,
)


def test_password_hash_roundtrip():
    password_hash = hash_password("una-clave-segura")

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "una-clave-segura")
    assert not verify_password(password_hash, "otra")
    assert not verify_password("no-es-un-hash", "una-clave-segura")


def test_session_tokens_are_random_and_hashed():
    a, b = new_session_token(), new_session_token()

    assert a != b
    assert len(hash_token(a)) == 64
    assert hash_token(a) == hash_token(a)


def test_secrets_equal():
    assert secrets_equal("abc", "abc")
    assert not secrets_equal("abc", "abd")


def test_limiter_blocks_after_limit_per_key():
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)

    assert [limiter.hit("1.1.1.1") for _ in range(3)] == [True, True, False]
    assert limiter.hit("2.2.2.2") is True


def test_limiter_window_expires():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=0)

    assert limiter.hit("ip") is True
    assert limiter.hit("ip") is True
