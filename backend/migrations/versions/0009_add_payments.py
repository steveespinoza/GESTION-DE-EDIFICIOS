"""Record confirmed payments and their applications."""

import sqlalchemy as sa
from alembic import op

revision = "0009_add_payments"
down_revision = "0008_add_invoice_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("unit_id", sa.Uuid(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("billing_year", sa.Integer(), nullable=False),
        sa.Column("billing_month", sa.Integer(), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_cents", sa.BigInteger(), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column(
            "recorded_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("unit_id", "request_id", name="uq_payments_unit_request"),
        sa.CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999", name="ck_payments_amount"
        ),
        sa.CheckConstraint(
            "credit_cents BETWEEN 0 AND amount_cents", name="ck_payments_credit"
        ),
        sa.CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_payments_year"
        ),
        sa.CheckConstraint("billing_month BETWEEN 1 AND 12", name="ck_payments_month"),
    )
    op.create_table(
        "payment_applications",
        sa.Column(
            "payment_id", sa.Uuid(), sa.ForeignKey("payments.id"), primary_key=True
        ),
        sa.Column(
            "charge_id", sa.Uuid(), sa.ForeignKey("unit_charges.id"), primary_key=True
        ),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999",
            name="ck_payment_applications_amount",
        ),
    )
    op.create_index(
        "ix_payment_applications_charge_id", "payment_applications", ["charge_id"]
    )


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM payments) THEN
                RAISE EXCEPTION 'Preserve recorded payments and applications before downgrading.';
            END IF;
        END;
        $$;
    """)
    op.drop_table("payment_applications")
    op.drop_table("payments")
