from datetime import datetime

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from app.application.refresh_tokens import RefreshTokenRecord, RefreshTokenRepository
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import Base, RefreshTokenRow


class PostgresRefreshTokenRepository(RefreshTokenRepository):
    """Stores refresh tokens (hash-only) for rotation + reuse detection. Revocation is a
    hard delete; consumed-but-not-revoked rows are retained so a replay can still be matched
    and recognised as reuse."""

    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)
        Base.metadata.create_all(self._engine, tables=[RefreshTokenRow.__table__])

    def add(self, record: RefreshTokenRecord) -> None:
        with Session(self._engine) as session:
            session.add(
                RefreshTokenRow(
                    id=record.id,
                    user_id=record.user_id,
                    family_id=record.family_id,
                    token_hash=record.token_hash,
                    expires_at=record.expires_at,
                    consumed_at=record.consumed_at,
                )
            )
            session.commit()

    def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
            )
            return self._to_record(row) if row is not None else None

    def mark_consumed(self, token_id: str, consumed_at: datetime) -> None:
        with Session(self._engine) as session:
            session.execute(
                update(RefreshTokenRow)
                .where(RefreshTokenRow.id == token_id)
                .values(consumed_at=consumed_at)
            )
            session.commit()

    def revoke_family(self, family_id: str) -> None:
        with Session(self._engine) as session:
            session.execute(delete(RefreshTokenRow).where(RefreshTokenRow.family_id == family_id))
            session.commit()

    def revoke_user(self, user_id: str) -> None:
        with Session(self._engine) as session:
            session.execute(delete(RefreshTokenRow).where(RefreshTokenRow.user_id == user_id))
            session.commit()

    def delete_expired(self, now: datetime) -> int:
        """Hard-delete tokens past their expiry, returning how many rows were removed. Keeps
        the table bounded; expired rows are unusable anyway, so reuse detection is unaffected."""
        with Session(self._engine) as session:
            result = session.execute(
                delete(RefreshTokenRow).where(RefreshTokenRow.expires_at < now)
            )
            session.commit()
            return result.rowcount or 0

    @staticmethod
    def _to_record(row: RefreshTokenRow) -> RefreshTokenRecord:
        return RefreshTokenRecord(
            id=row.id,
            user_id=row.user_id,
            family_id=row.family_id,
            token_hash=row.token_hash,
            expires_at=row.expires_at,
            consumed_at=row.consumed_at,
        )
