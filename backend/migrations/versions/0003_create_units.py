"""Create units and add owner contact information."""

import sqlalchemy as sa
from alembic import op

revision = "0003_create_units"
down_revision = "0002_create_buildings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("email", sa.String(254)))
    op.add_column("accounts", sa.Column("phone", sa.String(40)))
    op.create_unique_constraint("uq_accounts_email", "accounts", ["email"])
    op.create_table(
        "units",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "building_id", sa.Uuid(), sa.ForeignKey("buildings.id"), nullable=False
        ),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("area_sqm", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("building_id", "number", name="uq_units_building_number"),
        sa.CheckConstraint("area_sqm > 0", name="ck_units_positive_area"),
    )
    op.create_index("ix_units_owner_id", "units", ["owner_id"])


def downgrade() -> None:
    op.drop_table("units")
    op.drop_constraint("uq_accounts_email", "accounts", type_="unique")
    op.drop_column("accounts", "phone")
    op.drop_column("accounts", "email")
