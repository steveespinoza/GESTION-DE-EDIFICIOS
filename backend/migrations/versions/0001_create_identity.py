"""Create roles, accounts and sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0001_create_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("name", sa.String(24), primary_key=True),
    )
    op.bulk_insert(roles, [{"name": "SuperAdmin"}, {"name": "Propietario"}])
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role_name", sa.String(24), sa.ForeignKey("roles.name"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_table(
        "account_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_account_sessions_account_expires",
        "account_sessions",
        ["account_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("account_sessions")
    op.drop_table("accounts")
    op.drop_table("roles")
