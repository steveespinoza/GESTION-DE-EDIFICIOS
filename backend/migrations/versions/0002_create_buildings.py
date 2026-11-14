"""Create buildings and their payment instructions."""

import sqlalchemy as sa
from alembic import op

revision = "0002_create_buildings"
down_revision = "0001_create_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buildings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("address", sa.String(250)),
        sa.Column("total_units", sa.Integer(), nullable=False),
        sa.Column("bank_name", sa.String(150)),
        sa.Column("account_number", sa.String(64)),
        sa.Column("cci", sa.String(64)),
        sa.Column("account_holder", sa.String(150)),
        sa.Column("contact_email", sa.String(254)),
        sa.CheckConstraint(
            "total_units >= 0", name="ck_buildings_total_units_nonnegative"
        ),
    )


def downgrade() -> None:
    op.drop_table("buildings")
