from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OwnerUnit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    area_sqm: Decimal


class OwnerBuilding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str | None


class OwnerBuildingGroup(OwnerBuilding):
    units: list[OwnerUnit] = Field(default_factory=list)


class PaymentInstructions(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bank_name: str | None
    account_number: str | None
    cci: str | None
    account_holder: str | None
    contact_email: str | None


class OwnerUnitDetail(OwnerUnit):
    building: OwnerBuilding
    payment_instructions: PaymentInstructions
