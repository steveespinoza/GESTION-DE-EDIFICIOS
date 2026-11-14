import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dependencies import get_db
from app.identity.models import Account, RoleName
from app.identity.service import password_hash
from app.main import app


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
def account_password():
    return "fixture-account-password"


@pytest.fixture(scope="session")
def test_password_hash(account_password):
    return password_hash.hash(account_password)


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


@pytest.fixture
def session_header():
    return {"X-Edificios-Request": "1"}


@pytest.fixture
def sign_in(client, account_password, session_header):
    def login(username: str, password: str | None = None):
        return client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": account_password if password is None else password,
            },
            headers=session_header,
        )

    return login


@pytest.fixture
def admin(client, sign_in):
    assert sign_in("test-admin").status_code == 200
    return client
