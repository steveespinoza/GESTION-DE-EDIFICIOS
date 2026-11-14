import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.dependencies import get_db
from app.identity.models import Account, AccountSession, RoleName
from app.identity.router import SESSION_COOKIE
from app.identity.service import password_hash
from app.main import app

TEST_PASSWORD = "fixture-account-password"
SESSION_HEADER = {"X-Edificios-Request": "1"}


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL must point to a migrated PostgreSQL test database"
        )
    engine = create_engine(url, connect_args={"options": "-c timezone=America/Lima"})
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def test_password_hash():
    return password_hash.hash(TEST_PASSWORD)


@pytest.fixture
def sessions(engine, test_password_hash):
    with engine.connect() as connection, connection.begin() as transaction:
        factory = sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        with factory.begin() as db:
            for role, username, is_active in (
                (RoleName.SUPERADMIN, "test-admin", True),
                (RoleName.OWNER, "test-owner", True),
                (RoleName.OWNER, "test-inactive", False),
            ):
                db.add(
                    Account(
                        username=username,
                        full_name="Cuenta de prueba",
                        password_hash=test_password_hash,
                        role_name=role.value,
                        is_active=is_active,
                    )
                )
        try:
            yield factory
        finally:
            transaction.rollback()


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)

    def get_test_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client
    finally:
        del app.dependency_overrides[get_db]


def login(client: TestClient, username: str, password: str = TEST_PASSWORD):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers=SESSION_HEADER,
    )


@pytest.mark.parametrize(
    ("username", "role", "allowed_panel", "other_panel"),
    [
        ("test-admin", "SuperAdmin", "admin", "owner"),
        ("test-owner", "Propietario", "owner", "admin"),
    ],
)
def test_login_sets_secure_cookie_and_authorizes_only_the_assigned_panel(
    client, sessions, username, role, allowed_panel, other_panel
):
    response = login(client, username)

    assert response.status_code == 200
    user = response.json()
    assert user["role"] == role
    assert user["username"] == username
    assert set(user) == {"id", "username", "full_name", "role", "expires_at"}
    assert response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" in cookie
    token = client.cookies[SESSION_COOKIE]
    with sessions() as db:
        assert db.get(AccountSession, sha256(token.encode()).hexdigest()) is not None
        assert db.get(AccountSession, token) is None
    assert client.get("/api/auth/me").json() == user
    permitted = client.get(f"/api/{allowed_panel}/session")
    assert permitted.status_code == 200
    assert permitted.json() == user
    assert client.get(f"/api/{other_panel}/session").status_code == 403


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("unknown-account", TEST_PASSWORD),
        ("test-admin", "incorrect-value"),
        ("test-inactive", TEST_PASSWORD),
    ],
)
def test_login_uses_the_same_error_for_invalid_credentials(client, username, password):
    response = login(client, username, password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Usuario o contraseña incorrectos."}
    assert SESSION_COOKIE not in client.cookies


@pytest.mark.parametrize(
    "path", ["/api/auth/me", "/api/admin/session", "/api/owner/session"]
)
def test_anonymous_access_is_rejected(client, path):
    assert client.get(path).status_code == 401


def test_logout_revokes_the_server_side_session(client):
    assert login(client, "test-owner").status_code == 200
    token = client.cookies[SESSION_COOKIE]

    assert client.post("/api/auth/logout", headers=SESSION_HEADER).status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert (
        client.get(
            "/api/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
        ).status_code
        == 401
    )


def test_expired_session_is_rejected_even_with_a_valid_cookie(client, sessions):
    assert login(client, "test-admin").status_code == 200
    token_hash = sha256(client.cookies[SESSION_COOKIE].encode()).hexdigest()
    with sessions.begin() as db:
        db.execute(
            update(AccountSession)
            .where(AccountSession.token_hash == token_hash)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/admin/session").status_code == 401


def test_disabling_an_account_rejects_an_existing_session(client, sessions):
    assert login(client, "test-owner").status_code == 200
    with sessions.begin() as db:
        db.execute(
            update(Account)
            .where(Account.username == "test-owner")
            .values(is_active=False)
        )

    assert client.get("/api/owner/session").status_code == 401


def test_session_changes_require_the_browser_request_header(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "test-owner", "password": TEST_PASSWORD},
    )
    assert response.status_code == 403
    assert login(client, "test-owner").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_invalid_login_payload_is_not_echoed(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "test-owner", "password": [TEST_PASSWORD]},
        headers=SESSION_HEADER,
    )

    assert response.status_code == 422
    assert TEST_PASSWORD not in response.text
