"""model_usage.cost_usd

Snapshots each row's USD cost so spend reads sum a stored number instead of re-pricing tokens,
and a later price change never rewrites historical spend. Pre-existing rows are backfilled once
with the current pricing registry so spend accrued before this column existed survives the
switch to summing the stored cost.

Revision ID: 0015_model_usage_cost
Revises: 0014_model_usage_estimated
Create Date: 2026-06-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_model_usage_cost"
down_revision = "0014_model_usage_estimated"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_usage",
        sa.Column("cost_usd", sa.Numeric(), nullable=False, server_default="0"),
    )
    _backfill_cost(op.get_bind())


def _backfill_cost(bind) -> None:
    rows = bind.execute(
        sa.text("SELECT id, model, input_tokens, output_tokens FROM model_usage")
    ).fetchall()
    if not rows:
        return  # fresh database — nothing to price (and no application import needed)
    # Price the pre-existing rows once, with the current registry, so spend accrued before this
    # column existed survives the switch to summing the stored cost. Imported lazily so a
    # fresh-DB migration (zero rows above) never depends on application code.
    from app.application.usage_pricing import UsagePricer
    from app.infrastructure.model_pricing_registry import HardcodedModelPricingRegistry

    pricer = UsagePricer(HardcodedModelPricingRegistry())
    for row in rows:
        cost = pricer.cost_of(row.model, row.input_tokens, row.output_tokens)
        bind.execute(
            sa.text("UPDATE model_usage SET cost_usd = :cost WHERE id = :id"),
            {"cost": cost, "id": row.id},
        )


def downgrade() -> None:
    op.drop_column("model_usage", "cost_usd")
