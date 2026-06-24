"""per-user profiles: add user_profile.user_id

Revision ID: 0006_user_profile_user_id
Revises: 0005_users
Create Date: 2026-06-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_user_profile_user_id"
down_revision = "0005_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profile", sa.Column("user_id", sa.String(length=36), nullable=True))
    # Backfill the previously single profile: hand it to the earliest-registered user,
    # or drop it if there are no users yet (it will be recreated per-user).
    conn = op.get_bind()
    first_user = conn.execute(
        sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1")
    ).fetchone()
    if first_user is not None:
        conn.execute(
            sa.text("UPDATE user_profile SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": first_user[0]},
        )
    else:
        conn.execute(sa.text("DELETE FROM user_profile"))

    op.alter_column("user_profile", "user_id", nullable=False)
    op.create_unique_constraint("uq_user_profile_user_id", "user_profile", ["user_id"])
    op.create_foreign_key(
        "fk_user_profile_user_id",
        "user_profile",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_profile_user_id", "user_profile", type_="foreignkey")
    op.drop_constraint("uq_user_profile_user_id", "user_profile", type_="unique")
    op.drop_column("user_profile", "user_id")
