"""Create each building's service catalog."""

import sqlalchemy as sa
from alembic import op

revision = "0004_create_service_categories"
down_revision = "0003_create_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "building_id", sa.Uuid(), sa.ForeignKey("buildings.id"), nullable=False
        ),
        sa.Column(
            "calculation_type",
            sa.Enum(
                "LINEAR",
                "METERED",
                name="ck_service_categories_calculation_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(50), nullable=False),
    )
    op.create_index(
        "uq_service_categories_building_name_ci",
        "service_categories",
        ["building_id", sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("service_categories")
