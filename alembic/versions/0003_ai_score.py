"""ai_score cache table

Revision ID: 0003_ai_score
Revises: 0002_user_profile
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_ai_score"
down_revision = "0002_user_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_score",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_score")
