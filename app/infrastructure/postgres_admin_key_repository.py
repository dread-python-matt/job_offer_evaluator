from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.application.ports import AdminKeyRecord, AdminKeyRepository
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import Base, OpenAiAdminKeyRow


class PostgresAdminKeyRepository(AdminKeyRepository):
    """Stores each user's OpenAI admin key (at most one row per user; the unique
    constraint enforces it). Only ciphertext is persisted — decryption happens in the
    application layer via the KeyCipher, never here."""

    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)
        Base.metadata.create_all(self._engine, tables=[OpenAiAdminKeyRow.__table__])

    def get(self, user_id: str) -> AdminKeyRecord | None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(OpenAiAdminKeyRow).where(OpenAiAdminKeyRow.user_id == user_id)
            )
            return self._to_record(row) if row is not None else None

    def upsert(self, record: AdminKeyRecord) -> None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(OpenAiAdminKeyRow).where(OpenAiAdminKeyRow.user_id == record.user_id)
            )
            if row is None:
                session.add(
                    OpenAiAdminKeyRow(
                        user_id=record.user_id,
                        key_ciphertext=record.key_ciphertext,
                        key_hint=record.key_hint,
                        created_at=record.created_at,
                    )
                )
            else:
                row.key_ciphertext = record.key_ciphertext
                row.key_hint = record.key_hint
                row.created_at = record.created_at
            session.commit()

    def delete(self, user_id: str) -> bool:
        with Session(self._engine) as session:
            result = session.execute(
                delete(OpenAiAdminKeyRow).where(OpenAiAdminKeyRow.user_id == user_id)
            )
            session.commit()
            return result.rowcount > 0

    @staticmethod
    def _to_record(row: OpenAiAdminKeyRow) -> AdminKeyRecord:
        return AdminKeyRecord(
            user_id=row.user_id,
            key_ciphertext=row.key_ciphertext,
            key_hint=row.key_hint,
            created_at=row.created_at,
        )
