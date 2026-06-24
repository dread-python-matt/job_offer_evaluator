from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.application.ports import SelectedModelRepository
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import Base, SelectedModelRow


class PostgresSelectedModelRepository(SelectedModelRepository):
    """Stores each user's selected scoring model, one row per user (keyed by user_id)."""

    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)
        Base.metadata.create_all(self._engine, tables=[SelectedModelRow.__table__])

    def get(self, user_id: str) -> str | None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(SelectedModelRow).where(SelectedModelRow.user_id == user_id)
            )
            return row.model if row is not None else None

    def set(self, user_id: str, model: str) -> None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(SelectedModelRow).where(SelectedModelRow.user_id == user_id)
            )
            if row is None:
                row = SelectedModelRow(user_id=user_id)
                session.add(row)
            row.model = model
            session.commit()
