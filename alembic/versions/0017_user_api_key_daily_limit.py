"""user_api_key.daily_request_limit (optional per-day request cap override)

Revision ID: 0017_user_api_key_daily_limit
Revises: 0016_openai_admin_key
Create Date: 2026-06-30

Note: the revision id is kept <=32 chars so it fits Alembic's default
`alembic_version.version_num VARCHAR(32)` on a fresh database.
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_user_api_key_daily_limit"
down_revision = "0016_openai_admin_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means "use the model's free-tier requests-per-day default"; a value is the user's
    # own override. Nullable with no server_default so existing keys keep the default behaviour.
    op.add_column(
        "user_api_key",
        sa.Column("daily_request_limit", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_api_key", "daily_request_limit")
