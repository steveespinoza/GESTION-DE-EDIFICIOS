from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from sqlalchemy import update

from app.identity.models import Account, AccountSession
from app.identity.router import SESSION_COOKIE


@pytest.mark.parametrize(
    ("username", "role", "allowed_panel", "other_panel"),
    [
        ("test-admin", "SuperAdmin", "admin", "owner"),
        ("test-owner", "Propietario", "owner", "admin"),
    ],
)
def test_login_sets_secure_cookie_and_authorizes_only_the_assigned_panel(
    client, sign_in, sessions, username, role, allowed_panel, other_panel
):
    response = sign_in(username)

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
        ("unknown-account", None),
        ("test-admin", "incorrect-value"),
        ("test-inactive", None),
    ],
)
def test_login_uses_the_same_error_for_invalid_credentials(
    client, sign_in, username, password
):
    response = sign_in(username, password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Usuario o contraseña incorrectos."}
    assert SESSION_COOKIE not in client.cookies


@pytest.mark.parametrize(
    "path", ["/api/auth/me", "/api/admin/session", "/api/owner/session"]
)
def test_anonymous_access_is_rejected(client, path):
    assert client.get(path).status_code == 401


def test_logout_revokes_the_server_side_session(client, sign_in, session_header):
    assert sign_in("test-owner").status_code == 200
    token = client.cookies[SESSION_COOKIE]

    assert client.post("/api/auth/logout", headers=session_header).status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert (
        client.get(
            "/api/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
        ).status_code
        == 401
    )


def test_expired_session_is_rejected_even_with_a_valid_cookie(
    client, sign_in, sessions
):
    assert sign_in("test-admin").status_code == 200
    token_hash = sha256(client.cookies[SESSION_COOKIE].encode()).hexdigest()
    with sessions.begin() as db:
        db.execute(
            update(AccountSession)
            .where(AccountSession.token_hash == token_hash)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/admin/session").status_code == 401


def test_disabling_an_account_rejects_an_existing_session(client, sign_in, sessions):
    assert sign_in("test-owner").status_code == 200
    with sessions.begin() as db:
        db.execute(
            update(Account)
            .where(Account.username == "test-owner")
            .values(is_active=False)
        )

    assert client.get("/api/owner/session").status_code == 401


def test_session_changes_require_the_browser_request_header(
    client, sign_in, account_password
):
    response = client.post(
        "/api/auth/login",
        json={"username": "test-owner", "password": account_password},
    )
    assert response.status_code == 403
    assert sign_in("test-owner").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_invalid_login_payload_is_not_echoed(client, account_password, session_header):
    response = client.post(
        "/api/auth/login",
        json={"username": "test-owner", "password": [account_password]},
        headers=session_header,
    )

    assert response.status_code == 422
    assert account_password not in response.text
