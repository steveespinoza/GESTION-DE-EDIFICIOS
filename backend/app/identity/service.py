import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.identity.models import Account, AccountSession, RoleName
from app.identity.schemas import SessionUser

SESSION_LIFETIME = timedelta(hours=8)
TOKEN_BYTES = 32
TOKEN_LENGTH = 43
password_hash = PasswordHash.recommended()
dummy_hash = password_hash.hash(secrets.token_urlsafe(TOKEN_BYTES))


@dataclass(frozen=True)
class StartedSession:
    token: str = field(repr=False)
    user: SessionUser


def _token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _session_user(account: Account, expires_at: datetime) -> SessionUser:
    return SessionUser(
        id=account.id,
        username=account.username,
        full_name=account.full_name,
        role=RoleName(account.role_name),
        expires_at=expires_at.astimezone(UTC),
    )


def start_session(db: Session, username: str, password: str) -> StartedSession | None:
    username = username.strip()
    if not (1 <= len(username) <= 100 and 1 <= len(password) <= 512):
        return None

    account = db.scalar(select(Account).where(Account.username == username))
    stored_hash = account.password_hash if account is not None else dummy_hash
    valid_password = password_hash.verify(password, stored_hash)
    if not valid_password or account is None or not account.is_active:
        return None

    now = datetime.now(UTC)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = now + SESSION_LIFETIME
    db.execute(
        delete(AccountSession).where(
            AccountSession.account_id == account.id,
            AccountSession.expires_at <= now,
        )
    )
    session_user = _session_user(account, expires_at)
    db.add(
        AccountSession(
            token_hash=_token_hash(token), account_id=account.id, expires_at=expires_at
        )
    )
    db.commit()
    return StartedSession(token, session_user)


def find_session(db: Session, token: str | None) -> SessionUser | None:
    if token is None or len(token) != TOKEN_LENGTH:
        return None

    result = db.execute(
        select(Account, AccountSession.expires_at)
        .join(AccountSession, AccountSession.account_id == Account.id)
        .where(
            AccountSession.token_hash == _token_hash(token),
            AccountSession.expires_at > datetime.now(UTC),
            Account.is_active.is_(True),
        )
    ).one_or_none()
    return _session_user(*result) if result is not None else None


def end_session(db: Session, token: str | None) -> None:
    if token is not None and len(token) == TOKEN_LENGTH:
        db.execute(
            delete(AccountSession).where(
                AccountSession.token_hash == _token_hash(token)
            )
        )
        db.commit()
