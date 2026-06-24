"""per-user usage: add model_usage.user_id

Revision ID: 0008_model_usage_user_id
Revises: 0007_selected_model_user_id
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_model_usage_user_id"
down_revision = "0007_selected_model_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no backfill: usage recorded before multi-tenancy stays unattributed and
    # is excluded from any user's per-user summary.
    op.add_column("model_usage", sa.Column("user_id", sa.String(length=36), nullable=True))
    op.create_index("ix_model_usage_user_id", "model_usage", ["user_id"])
    op.create_foreign_key(
        "fk_model_usage_user_id",
        "model_usage",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_model_usage_user_id", "model_usage", type_="foreignkey")
    op.drop_index("ix_model_usage_user_id", table_name="model_usage")
    op.drop_column("model_usage", "user_id")
