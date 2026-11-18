"""Audit credit applications and retain the origin of carried balances."""

import sqlalchemy as sa
from alembic import op

revision = "0012_automatic_credit_and_carry"
down_revision = "0011_add_report_proof_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_applications",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_applications", sa.Column("applied_by_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "payment_applications",
        sa.Column("automatic", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute("""
        UPDATE payment_applications AS application
        SET applied_at = payment.recorded_at, applied_by_id = payment.recorded_by_id
        FROM payments AS payment WHERE payment.id = application.payment_id
    """)
    op.alter_column(
        "payment_applications",
        "applied_at",
        nullable=False,
        server_default=sa.func.now(),
    )
    op.create_foreign_key(
        "fk_payment_applications_applied_by",
        "payment_applications",
        "accounts",
        ["applied_by_id"],
        ["id"],
    )
    op.create_table(
        "balance_carry_forwards",
        sa.Column(
            "charge_id", sa.Uuid(), sa.ForeignKey("unit_charges.id"), primary_key=True
        ),
        sa.Column("billing_year", sa.Integer(), primary_key=True),
        sa.Column("billing_month", sa.Integer(), primary_key=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "recorded_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=True
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("billing_year BETWEEN 2020 AND 9999", name="ck_carry_year"),
        sa.CheckConstraint("billing_month BETWEEN 1 AND 12", name="ck_carry_month"),
        sa.CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999", name="ck_carry_amount"
        ),
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM balance_carry_forwards)
               OR EXISTS (SELECT 1 FROM payment_applications WHERE automatic) THEN
                RAISE EXCEPTION 'Preserve credit applications and carried balances before downgrading.';
            END IF;
        END; $$;
    """)
    op.drop_table("balance_carry_forwards")
    op.drop_constraint(
        "fk_payment_applications_applied_by", "payment_applications", type_="foreignkey"
    )
    op.drop_column("payment_applications", "automatic")
    op.drop_column("payment_applications", "applied_by_id")
    op.drop_column("payment_applications", "applied_at")
