"""Versioned payment deadlines by building and accounting period."""

import sqlalchemy as sa
from alembic import op

revision = "0014_collection_deadlines"
down_revision = "0013_audited_charge_adjustments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "collection_deadlines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "building_id", sa.Uuid(), sa.ForeignKey("buildings.id"), nullable=False
        ),
        sa.Column("billing_year", sa.Integer(), nullable=False),
        sa.Column("billing_month", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "recorded_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "building_id", "request_id", name="uq_collection_deadlines_request"
        ),
        sa.UniqueConstraint(
            "building_id",
            "billing_year",
            "billing_month",
            "revision",
            name="uq_collection_deadlines_revision",
        ),
        sa.CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_collection_deadlines_year"
        ),
        sa.CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_collection_deadlines_month"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_collection_deadlines_revision"),
    )


def downgrade():
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM collection_deadlines) THEN
            RAISE EXCEPTION 'Preserve collection deadline history before downgrade';
          END IF;
        END $$;
    """)
    op.drop_table("collection_deadlines")
