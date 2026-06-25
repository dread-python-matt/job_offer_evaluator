"""user_api_key table (per-user provider API keys, each with its own budget)

Revision ID: 0012_user_api_key
Revises: 0011_refresh_tokens
Create Date: 2026-06-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_user_api_key"
down_revision = "0011_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_api_key",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("api_provider", sa.String(length=32), nullable=False),
        sa.Column("key_ciphertext", sa.Text(), nullable=False),
        sa.Column("key_hint", sa.String(length=64), nullable=False),
        sa.Column("limit_usd", sa.Numeric(), nullable=False),
        sa.Column("tracking_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "api_provider", name="uq_user_api_key_provider"),
    )
    op.create_index("ix_user_api_key_user_id", "user_api_key", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_api_key_user_id", table_name="user_api_key")
    op.drop_table("user_api_key")
