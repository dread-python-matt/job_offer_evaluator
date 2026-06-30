"""openai_admin_key table (per-user OpenAI admin key for org spend/usage readouts)

Revision ID: 0016_openai_admin_key
Revises: 0015_model_usage_cost
Create Date: 2026-06-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_openai_admin_key"
down_revision = "0015_model_usage_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openai_admin_key",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_ciphertext", sa.Text(), nullable=False),
        sa.Column("key_hint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_openai_admin_key_user"),
    )
    op.create_index("ix_openai_admin_key_user_id", "openai_admin_key", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_openai_admin_key_user_id", table_name="openai_admin_key")
    op.drop_table("openai_admin_key")
