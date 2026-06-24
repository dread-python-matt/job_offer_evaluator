"""selected_model table

Revision ID: 0004_selected_model
Revises: 0003_ai_score
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_selected_model"
down_revision = "0003_ai_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "selected_model",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("selected_model")
