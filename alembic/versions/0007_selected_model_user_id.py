"""per-user model selection: add selected_model.user_id

Revision ID: 0007_selected_model_user_id
Revises: 0006_user_profile_user_id
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_selected_model_user_id"
down_revision = "0006_user_profile_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("selected_model", sa.Column("user_id", sa.String(length=36), nullable=True))
    # Backfill the previously single selection to the earliest-registered user, or drop
    # it if there are no users yet.
    conn = op.get_bind()
    first_user = conn.execute(
        sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1")
    ).fetchone()
    if first_user is not None:
        conn.execute(
            sa.text("UPDATE selected_model SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": first_user[0]},
        )
    else:
        conn.execute(sa.text("DELETE FROM selected_model"))

    op.alter_column("selected_model", "user_id", nullable=False)
    op.create_unique_constraint("uq_selected_model_user_id", "selected_model", ["user_id"])
    op.create_foreign_key(
        "fk_selected_model_user_id",
        "selected_model",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_selected_model_user_id", "selected_model", type_="foreignkey")
    op.drop_constraint("uq_selected_model_user_id", "selected_model", type_="unique")
    op.drop_column("selected_model", "user_id")
