"""model_usage.estimated

Marks rows whose token counts were estimated (the provider reported no usage) rather than
measured, so estimated and measured usage stay distinguishable. Existing rows predate the
fallback and were all measured, so they default to false.

Revision ID: 0014_model_usage_estimated
Revises: 0013_model_usage_user_created_index
Create Date: 2026-06-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_model_usage_estimated"
down_revision = "0013_model_usage_user_created_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_usage",
        sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("model_usage", "estimated")
