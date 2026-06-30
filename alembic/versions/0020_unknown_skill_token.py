"""unknown_skill_token: persisted unmapped skill-token tail (Tier-0 misses) for curation

Revision ID: 0020_unknown_skill_token
Revises: 0019_offer_skill_index_meta
Create Date: 2026-06-30

Note: the revision id is kept <=32 chars so it fits Alembic's default
`alembic_version.version_num VARCHAR(32)` on a fresh database.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_unknown_skill_token"
down_revision = "0019_offer_skill_index_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # App-owned: the unmapped skill tokens the alias map doesn't recognize, with occurrences and a
    # few example raw forms. Snapshot-replaced by the corpus survey; read (by frequency) for
    # curation. Indexed on `occurrences` to serve the "top unmapped tokens" query.
    op.create_table(
        "unknown_skill_token",
        sa.Column("normalized", sa.String(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("raw_samples", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("normalized"),
    )
    op.create_index("ix_unknown_skill_token_occurrences", "unknown_skill_token", ["occurrences"])


def downgrade() -> None:
    op.drop_index("ix_unknown_skill_token_occurrences", table_name="unknown_skill_token")
    op.drop_table("unknown_skill_token")
