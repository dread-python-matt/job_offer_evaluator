"""user_profile table

Revision ID: 0002_user_profile
Revises: 0001_baseline
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_user_profile"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_profile")
