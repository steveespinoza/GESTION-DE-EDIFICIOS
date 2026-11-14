from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)


class BuildingFields(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
    ]
    address: str | None = Field(default=None, max_length=250)
    total_units: int = Field(strict=True, ge=0, le=2_147_483_647)


class BuildingInput(BuildingFields):
    model_config = ConfigDict(extra="forbid")

    bank_name: str | None = Field(default=None, max_length=150)
    account_number: str | None = Field(default=None, max_length=64)
    cci: str | None = Field(default=None, max_length=64)
    account_holder: str | None = Field(default=None, max_length=150)
    contact_email: EmailStr | None = Field(default=None, max_length=254)

    @field_validator(
        "address",
        "bank_name",
        "account_number",
        "cci",
        "account_holder",
        "contact_email",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class BuildingSummary(BuildingFields):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class BuildingDetail(BuildingInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
