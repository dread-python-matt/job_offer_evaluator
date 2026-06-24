from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.application.ports import BudgetRepository
from app.domain.budget import BudgetSettings
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import Base, BudgetRow


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresBudgetRepository(BudgetRepository):
    """Stores the budget in a single row (id=1). On first load it lazily seeds the
    default limit and anchors usage tracking to 'now', then persists the choice so it
    survives restarts."""

    _ROW_ID = 1

    def __init__(
        self,
        database_or_engine: str | Engine,
        default_limit_usd: float = 5.0,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._engine = resolve_engine(database_or_engine)
        Base.metadata.create_all(self._engine, tables=[BudgetRow.__table__])
        self._default_limit_usd = default_limit_usd
        self._clock = clock

    def load(self) -> BudgetSettings:
        with Session(self._engine) as session:
            row = session.get(BudgetRow, self._ROW_ID)
            if row is None:
                row = BudgetRow(
                    id=self._ROW_ID,
                    limit_usd=self._default_limit_usd,
                    tracking_since=self._clock(),
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return BudgetSettings(
                limit_usd=float(row.limit_usd),
                tracking_since=row.tracking_since,
            )

    def save(self, settings: BudgetSettings) -> None:
        with Session(self._engine) as session:
            row = session.get(BudgetRow, self._ROW_ID)
            if row is None:
                row = BudgetRow(id=self._ROW_ID)
                session.add(row)
            row.limit_usd = settings.limit_usd
            row.tracking_since = settings.tracking_since
            session.commit()
