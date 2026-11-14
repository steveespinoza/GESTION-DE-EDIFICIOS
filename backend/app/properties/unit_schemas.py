from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

from app.identity.schemas import OwnerDetail, OwnerProfile


class UnitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
    ]
    area_sqm: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class ExistingOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["existing"]
    id: UUID


class NewOwner(OwnerProfile):
    kind: Literal["new"]
    password: SecretStr = Field(min_length=8, max_length=512)


class UnitCreate(UnitInput):
    owner: ExistingOwner | NewOwner = Field(discriminator="kind")


class UnitDetail(UnitInput):
    id: UUID
    building_id: UUID
    owner: OwnerDetail
