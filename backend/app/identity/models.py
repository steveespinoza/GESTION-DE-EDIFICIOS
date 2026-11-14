from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RoleName(StrEnum):
    SUPERADMIN = "SuperAdmin"
    OWNER = "Propietario"


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(24), primary_key=True)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("email", name="uq_accounts_email"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    password_hash: Mapped[str] = mapped_column(String(255))
    role_name: Mapped[str] = mapped_column(String(24), ForeignKey("roles.name"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class AccountSession(Base):
    __tablename__ = "account_sessions"
    __table_args__ = (
        Index("ix_account_sessions_account_expires", "account_id", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
