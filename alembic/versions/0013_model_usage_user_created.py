"""perf: composite (user_id, created_at) index on model_usage

Replaces the standalone ix_model_usage_user_id with a composite index. Per-user spend is
derived by summing usage since an anchor timestamp (filter on user_id AND created_at), and
the composite also covers the user-only summary and FK cascade via its leftmost prefix, so
the single-column index becomes redundant.

Revision ID: 0013_model_usage_user_created
Revises: 0012_user_api_key
Create Date: 2026-06-26
"""
from alembic import op

revision = "0013_model_usage_user_created"
down_revision = "0012_user_api_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_model_usage_user_created", "model_usage", ["user_id", "created_at"]
    )
    op.drop_index("ix_model_usage_user_id", table_name="model_usage")


def downgrade() -> None:
    op.create_index("ix_model_usage_user_id", "model_usage", ["user_id"])
    op.drop_index("ix_model_usage_user_created", table_name="model_usage")
