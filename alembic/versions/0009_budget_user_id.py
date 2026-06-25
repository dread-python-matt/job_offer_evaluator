"""per-user budgets: add budget.user_id

Revision ID: 0009_budget_user_id
Revises: 0008_model_usage_user_id
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_budget_user_id"
down_revision = "0008_model_usage_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budget", sa.Column("user_id", sa.String(length=36), nullable=True))
    # Backfill the previously single budget to the earliest-registered user, or drop it
    # if there are no users yet (each user's budget is lazily seeded on first use).
    conn = op.get_bind()
    first_user = conn.execute(
        sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1")
    ).fetchone()
    if first_user is not None:
        conn.execute(
            sa.text("UPDATE budget SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": first_user[0]},
        )
    else:
        conn.execute(sa.text("DELETE FROM budget"))

    op.alter_column("budget", "user_id", nullable=False)
    op.create_unique_constraint("uq_budget_user_id", "budget", ["user_id"])
    op.create_foreign_key(
        "fk_budget_user_id", "budget", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("fk_budget_user_id", "budget", type_="foreignkey")
    op.drop_constraint("uq_budget_user_id", "budget", type_="unique")
    op.drop_column("budget", "user_id")
