from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.application.ports import SelectedModelRepository
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import Base, SelectedModelRow


class PostgresSelectedModelRepository(SelectedModelRepository):
    """Stores the selected scoring model in a single row (id=1)."""

    _ROW_ID = 1

    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)
        Base.metadata.create_all(self._engine, tables=[SelectedModelRow.__table__])

    def get(self) -> str | None:
        with Session(self._engine) as session:
            row = session.get(SelectedModelRow, self._ROW_ID)
            return row.model if row is not None else None

    def set(self, model: str) -> None:
        with Session(self._engine) as session:
            row = session.get(SelectedModelRow, self._ROW_ID)
            if row is None:
                row = SelectedModelRow(id=self._ROW_ID)
                session.add(row)
            row.model = model
            session.commit()
