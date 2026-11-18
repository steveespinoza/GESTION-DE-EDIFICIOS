"""Keep issued PDF receipts and their financial snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_versioned_receipts"
down_revision = "0014_collection_deadlines"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("unit_id", sa.Uuid(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("billing_year", sa.Integer(), nullable=False),
        sa.Column("billing_month", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "issued_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("storage_key", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("unit_id", "request_id", name="uq_receipts_request"),
        sa.UniqueConstraint(
            "unit_id",
            "billing_year",
            "billing_month",
            "version",
            name="uq_receipts_version",
        ),
        sa.CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_receipts_year"
        ),
        sa.CheckConstraint("billing_month BETWEEN 1 AND 12", name="ck_receipts_month"),
        sa.CheckConstraint("version >= 1", name="ck_receipts_version"),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 10485760", name="ck_receipts_size"
        ),
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM receipts) THEN
        RAISE EXCEPTION 'Preserve issued receipts before downgrade';
      END IF;
    END $$;""")
    op.drop_table("receipts")
