from datetime import datetime, timezone

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.application.ports import ModelUsage, ModelUsageRepository, ModelUsageSummary
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import Base, ModelUsageRow


class PostgresModelUsageRepository(ModelUsageRepository):
    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)
        Base.metadata.create_all(self._engine, tables=[ModelUsageRow.__table__])

    def save(self, usage: ModelUsage) -> None:
        with Session(self._engine) as session:
            session.add(ModelUsageRow(
                user_id=usage.user_id or None,
                company=usage.company,
                model=usage.model,
                label=usage.label,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated=usage.estimated,
                cost_usd=usage.cost_usd,
                created_at=datetime.now(timezone.utc),
            ))
            session.commit()

    def get_summary(self, user_id: str) -> list[ModelUsageSummary]:
        return self._aggregate(user_id, since=None)

    def usage_since(self, user_id: str, start: datetime) -> list[ModelUsageSummary]:
        return self._aggregate(user_id, since=start)

    def _aggregate(self, user_id: str, since: datetime | None) -> list[ModelUsageSummary]:
        query = (
            select(
                ModelUsageRow.company,
                ModelUsageRow.model,
                func.sum(ModelUsageRow.input_tokens).label("input_tokens"),
                func.sum(ModelUsageRow.output_tokens).label("output_tokens"),
                func.sum(ModelUsageRow.cost_usd).label("cost_usd"),
            )
            .where(ModelUsageRow.user_id == user_id)
            .group_by(ModelUsageRow.company, ModelUsageRow.model)
        )
        if since is not None:
            query = query.where(ModelUsageRow.created_at >= since)
        with Session(self._engine) as session:
            rows = session.execute(query).all()

        return [
            ModelUsageSummary(
                company=row.company,
                model=row.model,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cost_usd=float(row.cost_usd or 0),
            )
            for row in rows
        ]
