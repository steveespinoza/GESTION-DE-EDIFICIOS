from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.billing.models import CalculationType


class ServiceCategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=50)
    ]
    calculation_type: CalculationType


class ServiceCategoryDetail(ServiceCategoryInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    building_id: UUID
