"""baseline: app-owned tables (model_usage, budget)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-24

Mirrors the ORM models in app.infrastructure.orm_models. The scraper-owned
`offers`/`salaries` tables are intentionally not managed here.
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("limit_usd", sa.Numeric(), nullable=False),
        sa.Column("tracking_since", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("budget")
    op.drop_table("model_usage")
