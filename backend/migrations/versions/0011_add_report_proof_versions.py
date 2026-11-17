"""Retain each replacement proof and its author."""

import sqlalchemy as sa
from alembic import op

revision = "0011_add_report_proof_versions"
down_revision = "0010_add_payment_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_reports",
        sa.Column("proof_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_payment_reports_proof_revision", "payment_reports", "proof_revision >= 0"
    )
    op.create_table(
        "payment_report_proofs",
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey("payment_reports.id"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "uploaded_by_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.UniqueConstraint(
            "report_id", "request_id", name="uq_payment_report_proofs_request"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_payment_report_proofs_revision"),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 10485760", name="ck_payment_report_proofs_size"
        ),
    )


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM payment_report_proofs)
               OR EXISTS (SELECT 1 FROM payment_reports WHERE proof_revision > 0) THEN
                RAISE EXCEPTION 'Preserve replacement proofs and their history before downgrading.';
            END IF;
        END;
        $$;
    """)
    op.drop_table("payment_report_proofs")
    op.drop_constraint(
        "ck_payment_reports_proof_revision", "payment_reports", type_="check"
    )
    op.drop_column("payment_reports", "proof_revision")
