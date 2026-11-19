"""Persist receipt batches and atomic results per unit."""

import sqlalchemy as sa
from alembic import op

revision = "0016_receipt_batches"
down_revision = "0015_versioned_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "receipt_batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "building_id", sa.Uuid(), sa.ForeignKey("buildings.id"), nullable=False
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("billing_year", sa.Integer(), nullable=False),
        sa.Column("billing_month", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "deadline_id",
            sa.Uuid(),
            sa.ForeignKey("collection_deadlines.id"),
            nullable=False,
        ),
        sa.Column("base_deadline_revision", sa.Integer(), nullable=False),
        sa.Column("deadline_revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "created_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "building_id", "request_id", name="uq_receipt_batches_request"
        ),
        sa.CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_receipt_batches_year"
        ),
        sa.CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_receipt_batches_month"
        ),
        sa.CheckConstraint(
            "base_deadline_revision >= 0 AND deadline_revision >= 1",
            name="ck_receipt_batches_revision",
        ),
    )
    op.create_table(
        "receipt_batch_items",
        sa.Column(
            "batch_id", sa.Uuid(), sa.ForeignKey("receipt_batches.id"), primary_key=True
        ),
        sa.Column("unit_id", sa.Uuid(), sa.ForeignKey("units.id"), primary_key=True),
        sa.Column("unit_number", sa.String(60), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), sa.ForeignKey("receipts.id"), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_attempt_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=True
        ),
        sa.Column("error_code", sa.String(16), nullable=True),
        sa.Column("error_message", sa.String(250), nullable=True),
        sa.UniqueConstraint("receipt_id", name="uq_receipt_batch_items_receipt"),
        sa.CheckConstraint(
            "status IN ('PENDING','ISSUED','FAILED','SKIPPED')",
            name="ck_receipt_batch_items_status",
        ),
        sa.CheckConstraint(
            "revision >= 0 AND attempts >= 0", name="ck_receipt_batch_items_counters"
        ),
        sa.CheckConstraint(
            "(status = 'ISSUED') = (receipt_id IS NOT NULL)",
            name="ck_receipt_batch_items_receipt",
        ),
        sa.CheckConstraint(
            "(status = 'FAILED') = (error_code IS NOT NULL) AND (status = 'FAILED') = (error_message IS NOT NULL)",
            name="ck_receipt_batch_items_error",
        ),
        sa.CheckConstraint(
            "(attempts = 0) = (last_attempt_at IS NULL) AND (attempts = 0) = (last_attempt_by_id IS NULL)",
            name="ck_receipt_batch_items_attempt",
        ),
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM receipt_batches) THEN
        RAISE EXCEPTION 'Preserve receipt batches before downgrade';
      END IF;
    END $$;""")
    op.drop_table("receipt_batch_items")
    op.drop_table("receipt_batches")
