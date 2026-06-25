"""users.email_verified

Revision ID: 0010_user_email_verified
Revises: 0009_budget_user_id
Create Date: 2026-06-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_user_email_verified"
down_revision = "0009_budget_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    # Existing accounts predate email confirmation — they registered under the old
    # auto-login flow — so grandfather them in as verified rather than locking them out.
    op.execute("UPDATE users SET email_verified = true")


def downgrade() -> None:
    op.drop_column("users", "email_verified")
