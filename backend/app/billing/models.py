from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Enum, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SERVICE_NAME_INDEX = "uq_service_categories_building_name_ci"


class CalculationType(StrEnum):
    LINEAR = "LINEAR"
    METERED = "METERED"


class ServiceCategory(Base):
    __tablename__ = "service_categories"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    building_id: Mapped[UUID] = mapped_column(ForeignKey("buildings.id"))
    name: Mapped[str] = mapped_column(String(50))
    calculation_type: Mapped[CalculationType] = mapped_column(
        Enum(
            CalculationType,
            name="ck_service_categories_calculation_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )

    __table_args__ = (
        Index(SERVICE_NAME_INDEX, "building_id", func.lower(name), unique=True),
    )
