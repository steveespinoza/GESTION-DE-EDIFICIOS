from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.identity.models import Account, RoleName
from app.identity.schemas import OwnerOption, OwnerProfile
from app.identity.service import password_hash


def list_available_owners(db: Session) -> list[OwnerOption]:
    statement = (
        select(Account)
        .where(Account.role_name == RoleName.OWNER.value, Account.is_active.is_(True))
        .order_by(func.lower(Account.full_name), Account.id)
    )
    return [OwnerOption.model_validate(account) for account in db.scalars(statement)]


def find_available_owner(db: Session, owner_id: UUID) -> Account | None:
    return db.scalar(
        select(Account).where(
            Account.id == owner_id,
            Account.role_name == RoleName.OWNER.value,
            Account.is_active.is_(True),
        )
    )


def add_owner(db: Session, profile: OwnerProfile, password: SecretStr) -> Account:
    account = Account(
        **profile.model_dump(),
        password_hash=password_hash.hash(password.get_secret_value()),
        role_name=RoleName.OWNER.value,
    )
    db.add(account)
    return account
