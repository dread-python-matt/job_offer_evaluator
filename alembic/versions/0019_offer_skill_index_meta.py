"""offer_skill_index_meta: bookkeeping (map version, built_at, row_count) for the offer_skill index

Revision ID: 0019_offer_skill_index_meta
Revises: 0018_offer_skill_index
Create Date: 2026-06-30

Note: the revision id is kept <=32 chars so it fits Alembic's default
`alembic_version.version_num VARCHAR(32)` on a fresh database.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_offer_skill_index_meta"
down_revision = "0018_offer_skill_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Single-row table (id is always 1) recording which alias-map version built the offer_skill
    # index, when, and how many rows — so a stale/unbuilt index is observable, not silent.
    # App-owned, like `offer_skill`.
    op.create_table(
        "offer_skill_index_meta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("map_version", sa.String(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("offer_skill_index_meta")
