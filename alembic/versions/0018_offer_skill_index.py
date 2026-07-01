"""offer_skill: canonical projection of offer skills for concept-based browse filtering

Revision ID: 0018_offer_skill_index
Revises: 0017_user_api_key_daily_limit
Create Date: 2026-06-30

Note: the revision id is kept <=32 chars so it fits Alembic's default
`alembic_version.version_num VARCHAR(32)` on a fresh database.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_offer_skill_index"
down_revision = "0017_user_api_key_daily_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # App-owned derived index (the `offers` table is externally-owned). No FK to `offers`: it's a
    # cache rebuilt by `app.scripts.index_offer_skills`; orphans are harmless and pruned on rebuild.
    op.create_table(
        "offer_skill",
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("canonical_id", sa.String(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("offer_id", "canonical_id"),
    )
    op.create_index("ix_offer_skill_canonical_id", "offer_skill", ["canonical_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_skill_canonical_id", table_name="offer_skill")
    op.drop_table("offer_skill")
