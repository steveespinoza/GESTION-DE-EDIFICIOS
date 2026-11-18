"""Preserve charge adjustments and releases of previously applied payments."""

import sqlalchemy as sa
from alembic import op

revision = "0013_audited_charge_adjustments"
down_revision = "0012_automatic_credit_and_carry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_applications", sa.Column("id", sa.Uuid(), nullable=True))
    op.execute("UPDATE payment_applications SET id = gen_random_uuid()")
    op.drop_constraint(
        "payment_applications_pkey", "payment_applications", type_="primary"
    )
    op.alter_column(
        "payment_applications",
        "id",
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )
    op.create_primary_key("payment_applications_pkey", "payment_applications", ["id"])
    op.create_index(
        "ix_payment_applications_payment_id", "payment_applications", ["payment_id"]
    )
    op.create_table(
        "charge_adjustments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "charge_id", sa.Uuid(), sa.ForeignKey("unit_charges.id"), nullable=False
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_cents", sa.BigInteger(), nullable=False),
        sa.Column("revised_cents", sa.BigInteger(), nullable=False),
        sa.Column("delta_cents", sa.BigInteger(), nullable=False),
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
            "charge_id", "request_id", name="uq_charge_adjustments_request"
        ),
        sa.UniqueConstraint(
            "charge_id", "revision", name="uq_charge_adjustments_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_charge_adjustments_revision"),
        sa.CheckConstraint(
            "previous_cents BETWEEN 0 AND 999999999999 AND revised_cents BETWEEN 0 AND 999999999999",
            name="ck_charge_adjustments_amounts",
        ),
        sa.CheckConstraint(
            "delta_cents <> 0 AND previous_cents + delta_cents = revised_cents",
            name="ck_charge_adjustments_delta",
        ),
    )
    op.create_table(
        "payment_application_releases",
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("payment_applications.id"),
            primary_key=True,
        ),
        sa.Column(
            "adjustment_id",
            sa.Uuid(),
            sa.ForeignKey("charge_adjustments.id"),
            primary_key=True,
        ),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999",
            name="ck_application_releases_amount",
        ),
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM charge_adjustments)
               OR EXISTS (SELECT 1 FROM payment_application_releases) THEN
                RAISE EXCEPTION 'Preserve charge adjustments and releases before downgrading.';
            END IF;
        END; $$;
    """)
    op.drop_table("payment_application_releases")
    op.drop_table("charge_adjustments")
    op.drop_index(
        "ix_payment_applications_payment_id", table_name="payment_applications"
    )
    op.drop_constraint(
        "payment_applications_pkey", "payment_applications", type_="primary"
    )
    op.create_primary_key(
        "payment_applications_pkey", "payment_applications", ["payment_id", "charge_id"]
    )
    op.drop_column("payment_applications", "id")
