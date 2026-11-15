"""Track invoice corrections and protect posted charges."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_add_invoice_corrections"
down_revision = "0007_add_invoice_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_invoices",
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "service_invoices",
        sa.Column("accounting_locked_at", sa.DateTime(timezone=True)),
    )
    op.create_check_constraint(
        "ck_service_invoices_revision", "service_invoices", "revision >= 0"
    )
    op.create_table(
        "invoice_corrections",
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("service_invoices.id"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column(
            "corrected_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "corrected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("before", JSONB(), nullable=False),
        sa.Column("after", JSONB(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_invoice_corrections_revision"),
    )


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM invoice_corrections) OR EXISTS (
                SELECT 1 FROM service_invoices WHERE accounting_locked_at IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Preserve invoice correction history and accounting locks before downgrading.';
            END IF;
        END;
        $$;
    """)
    op.drop_table("invoice_corrections")
    op.drop_constraint(
        "ck_service_invoices_revision", "service_invoices", type_="check"
    )
    op.drop_column("service_invoices", "accounting_locked_at")
    op.drop_column("service_invoices", "revision")
