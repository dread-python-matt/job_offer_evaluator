from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.application.ports import ModelUsage, ModelUsageRepository, ModelUsageSummary
from app.infrastructure.orm_models import Base, ModelUsageRow


class PostgresModelUsageRepository(ModelUsageRepository):
    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url)
        Base.metadata.create_all(self._engine, tables=[ModelUsageRow.__table__])

    def save(self, usage: ModelUsage) -> None:
        with Session(self._engine) as session:
            session.add(ModelUsageRow(
                company=usage.company,
                model=usage.model,
                label=usage.label,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                created_at=datetime.now(timezone.utc),
            ))
            session.commit()

    def get_summary(self) -> list[ModelUsageSummary]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(
                    ModelUsageRow.company,
                    ModelUsageRow.model,
                    func.sum(ModelUsageRow.input_tokens).label("input_tokens"),
                    func.sum(ModelUsageRow.output_tokens).label("output_tokens"),
                ).group_by(ModelUsageRow.company, ModelUsageRow.model)
            ).all()

        return [
            ModelUsageSummary(
                company=row.company,
                model=row.model,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
            )
            for row in rows
        ]
