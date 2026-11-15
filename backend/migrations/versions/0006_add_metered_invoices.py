"""Store metered volumes, readings and common-area charges."""

import sqlalchemy as sa
from alembic import op

revision = "0006_add_metered_invoices"
down_revision = "0005_create_linear_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_invoices", sa.Column("total_volume_milli", sa.BigInteger()))
    op.create_check_constraint(
        "ck_service_invoices_volume",
        "service_invoices",
        "total_volume_milli BETWEEN 1 AND 999999999999",
    )
    op.add_column("unit_charges", sa.Column("common_cents", sa.BigInteger()))
    op.create_check_constraint(
        "ck_unit_charges_common_amount",
        "unit_charges",
        "common_cents BETWEEN 0 AND amount_cents",
    )
    op.create_table(
        "meter_readings",
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("service_invoices.id"),
            primary_key=True,
        ),
        sa.Column("unit_id", sa.Uuid(), sa.ForeignKey("units.id"), primary_key=True),
        sa.Column("previous_milli", sa.Integer(), nullable=False),
        sa.Column("current_milli", sa.Integer(), nullable=False),
        sa.Column("consumption_milli", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "previous_milli BETWEEN 0 AND 99999999", name="ck_meter_readings_previous"
        ),
        sa.CheckConstraint(
            "current_milli BETWEEN 0 AND 99999999", name="ck_meter_readings_current"
        ),
        sa.CheckConstraint(
            "consumption_milli = CASE WHEN current_milli < previous_milli "
            "THEN 100000000 + current_milli - previous_milli ELSE current_milli - previous_milli END",
            name="ck_meter_readings_consumption",
        ),
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM service_invoices WHERE total_volume_milli IS NOT NULL) THEN
                RAISE EXCEPTION 'Export or migrate metered invoices before downgrading this revision.';
            END IF;
        END;
        $$;
        """
    )
    op.drop_table("meter_readings")
    op.drop_constraint("ck_unit_charges_common_amount", "unit_charges", type_="check")
    op.drop_column("unit_charges", "common_cents")
    op.drop_constraint("ck_service_invoices_volume", "service_invoices", type_="check")
    op.drop_column("service_invoices", "total_volume_milli")
