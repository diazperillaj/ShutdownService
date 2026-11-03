from fastapi.testclient import TestClient

from app.auth import SESSION_COOKIE

from .conftest import ORIGIN, PASSWORD, USERNAME


def test_login_sets_secure_session_cookie(client: TestClient):
    response = client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json() == {"username": USERNAME}
    cookie = response.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert client.get("/api/auth/me").json() == {"username": USERNAME}


def test_wrong_password_and_unknown_user_get_same_message(client: TestClient):
    wrong = client.post("/api/auth/login", json={"username": USERNAME, "password": "incorrecta"})
    unknown = client.post("/api/auth/login", json={"username": "nadie", "password": "incorrecta"})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_user_is_locked_after_too_many_failures(client: TestClient):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": USERNAME, "password": "incorrecta"})

    # Bloqueado incluso con la contraseña correcta.
    response = client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 429


def test_ip_rate_limit(client: TestClient):
    statuses = [
        client.post("/api/auth/login", json={"username": "nadie", "password": "x"}).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


def test_login_requires_same_origin(client: TestClient):
    response = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        headers={"origin": "https://malicioso.example"},
    )
    assert response.status_code == 403


def test_protected_routes_require_session(client: TestClient):
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_logout_invalidates_session(logged_in: TestClient):
    token = logged_in.cookies.get(SESSION_COOKIE)

    assert logged_in.post("/api/auth/logout").status_code == 204

    logged_in.cookies.set(SESSION_COOKIE, token, domain="testserver")
    assert logged_in.get("/api/auth/me").status_code == 401


def test_change_password(logged_in: TestClient):
    short = logged_in.post(
        "/api/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": "corta"},
    )
    assert short.status_code == 422

    wrong = logged_in.post(
        "/api/auth/change-password",
        json={"currentPassword": "incorrecta", "newPassword": "otra-clave-segura"},
    )
    assert wrong.status_code == 400

    ok = logged_in.post(
        "/api/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": "otra-clave-segura"},
    )
    assert ok.status_code == 204

    logged_in.post("/api/auth/logout")
    old = logged_in.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    new = logged_in.post(
        "/api/auth/login", json={"username": USERNAME, "password": "otra-clave-segura"}
    )
    assert old.status_code == 401
    assert new.status_code == 200


def test_docs_disabled_by_default(client: TestClient):
    assert client.get("/api/docs").status_code == 404
    assert client.get("/health").json() == {"status": "ok"}


def test_origin_constant_is_used(client: TestClient):
    assert client.app.state.settings.public_origin == ORIGIN
