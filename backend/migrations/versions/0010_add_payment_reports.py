"""Keep owner payment reports and their review separate from ledger payments."""

import sqlalchemy as sa
from alembic import op

revision = "0010_add_payment_reports"
down_revision = "0009_add_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("unit_id", sa.Uuid(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column(
            "submitted_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("billing_year", sa.Integer(), nullable=False),
        sa.Column("billing_month", sa.Integer(), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("reference", sa.String(120)),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(160), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by_id", sa.Uuid(), sa.ForeignKey("accounts.id")),
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("payments.id")),
        sa.Column("rejection_reason", sa.String(500)),
        sa.UniqueConstraint(
            "unit_id", "request_id", name="uq_payment_reports_unit_request"
        ),
        sa.UniqueConstraint("payment_id", name="uq_payment_reports_payment"),
        sa.CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_payment_reports_year"
        ),
        sa.CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_payment_reports_month"
        ),
        sa.CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999", name="ck_payment_reports_amount"
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 10485760", name="ck_payment_reports_proof_size"
        ),
        sa.CheckConstraint(
            """
            (reviewed_at IS NULL AND reviewed_by_id IS NULL AND payment_id IS NULL AND rejection_reason IS NULL)
            OR (reviewed_at IS NOT NULL AND reviewed_by_id IS NOT NULL AND
                ((payment_id IS NOT NULL AND rejection_reason IS NULL)
                 OR (payment_id IS NULL AND rejection_reason IS NOT NULL)))
            """,
            name="ck_payment_reports_state",
        ),
    )
    op.create_index(
        "ix_payment_reports_unit_submitted",
        "payment_reports",
        ["unit_id", "submitted_at"],
    )


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM payment_reports) THEN
                RAISE EXCEPTION 'Preserve payment reports and proof references before downgrading.';
            END IF;
        END;
        $$;
    """)
    op.drop_table("payment_reports")
