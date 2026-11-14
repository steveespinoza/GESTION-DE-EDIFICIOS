from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)

from app.identity.models import RoleName


class LoginRequest(BaseModel):
    username: str
    password: SecretStr


class SessionUser(BaseModel):
    id: UUID
    username: str
    full_name: str
    role: RoleName
    expires_at: datetime


class OwnerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)
    ]
    username: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=100)
    ]
    email: EmailStr | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("email", "phone", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value


class OwnerOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    username: str


class OwnerDetail(OwnerOption):
    email: str | None
    phone: str | None
