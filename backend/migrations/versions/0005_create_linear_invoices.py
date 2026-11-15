"""Store service invoices and their per-unit charges."""

import sqlalchemy as sa
from alembic import op

revision = "0005_create_linear_invoices"
down_revision = "0004_create_service_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_invoices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("service_categories.id"),
            nullable=False,
        ),
        sa.Column("billing_year", sa.Integer(), nullable=False),
        sa.Column("billing_month", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "category_id",
            "billing_year",
            "billing_month",
            name="uq_service_invoices_category_period",
        ),
        sa.CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999",
            name="ck_service_invoices_billing_year",
        ),
        sa.CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_service_invoices_billing_month"
        ),
        sa.CheckConstraint(
            "end_date >= start_date", name="ck_service_invoices_date_order"
        ),
        sa.CheckConstraint(
            "total_cents BETWEEN 1 AND 999999999999", name="ck_service_invoices_total"
        ),
    )
    op.create_table(
        "unit_charges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("service_invoices.id"),
            nullable=False,
        ),
        sa.Column("unit_id", sa.Uuid(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("unit_number", sa.String(60), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "invoice_id", "unit_id", name="uq_unit_charges_invoice_unit"
        ),
        sa.CheckConstraint(
            "amount_cents BETWEEN 0 AND 999999999999", name="ck_unit_charges_amount"
        ),
    )
    op.create_index("ix_unit_charges_unit_id", "unit_charges", ["unit_id"])


def downgrade() -> None:
    op.drop_table("unit_charges")
    op.drop_table("service_invoices")
