"""Store private file metadata for provider invoices."""

import sqlalchemy as sa
from alembic import op

revision = "0007_add_invoice_attachments"
down_revision = "0006_add_metered_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("service_invoices.id"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "DOCUMENT",
                "VOUCHER",
                name="ck_invoice_attachments_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(160), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "invoice_id", "kind", "sha256", name="uq_invoice_attachments_digest"
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 10485760", name="ck_invoice_attachments_size"
        ),
    )
    op.create_index(
        "uq_invoice_attachments_voucher",
        "invoice_attachments",
        ["invoice_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'VOUCHER'"),
    )


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM invoice_attachments) THEN
                RAISE EXCEPTION 'Export or migrate invoice attachment metadata before downgrading.';
            END IF;
        END;
        $$;
    """)
    op.drop_table("invoice_attachments")
