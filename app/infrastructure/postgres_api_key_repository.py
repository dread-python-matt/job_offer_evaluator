from sqlalchemy import Engine, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ports import ApiKeyRecord, ApiKeyRepository
from app.domain.errors import ApiKeyAlreadyExistsError
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import UserApiKeyRow


class PostgresApiKeyRepository(ApiKeyRepository):
    """Stores each user's provider API keys (one row per (user, provider); the unique
    constraint rejects a duplicate provider). Only ciphertext is persisted — decryption
    happens in the use cases via the KeyCipher, never here."""

    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)

    def add(self, record: ApiKeyRecord) -> None:
        with Session(self._engine) as session:
            session.add(
                UserApiKeyRow(
                    user_id=record.user_id,
                    api_provider=record.api_provider,
                    key_ciphertext=record.key_ciphertext,
                    key_hint=record.key_hint,
                    limit_usd=record.limit_usd,
                    tracking_since=record.tracking_since,
                    created_at=record.created_at,
                    daily_request_limit=record.daily_request_limit,
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                # A concurrent insert won the unique (user_id, api_provider) race between the
                # use case's existence check and this commit. Surface the clean domain error
                # (mapped to 409) instead of letting IntegrityError bubble to a generic 500.
                raise ApiKeyAlreadyExistsError(record.api_provider) from exc

    def list_for_user(self, user_id: str) -> list[ApiKeyRecord]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(UserApiKeyRow)
                .where(UserApiKeyRow.user_id == user_id)
                .order_by(UserApiKeyRow.api_provider)
            ).all()
            return [self._to_record(row) for row in rows]

    def get(self, user_id: str, api_provider: str) -> ApiKeyRecord | None:
        with Session(self._engine) as session:
            row = session.scalar(self._by_user_provider(user_id, api_provider))
            return self._to_record(row) if row is not None else None

    def delete(self, user_id: str, api_provider: str) -> bool:
        with Session(self._engine) as session:
            result = session.execute(
                delete(UserApiKeyRow)
                .where(UserApiKeyRow.user_id == user_id)
                .where(UserApiKeyRow.api_provider == api_provider)
            )
            session.commit()
            return result.rowcount > 0  # type: ignore[attr-defined]  # DML CursorResult has rowcount

    def update_budget(self, user_id: str, api_provider: str, limit_usd: float) -> bool:
        with Session(self._engine) as session:
            result = session.execute(
                update(UserApiKeyRow)
                .where(UserApiKeyRow.user_id == user_id)
                .where(UserApiKeyRow.api_provider == api_provider)
                .values(limit_usd=limit_usd)
            )
            session.commit()
            return result.rowcount > 0  # type: ignore[attr-defined]  # DML CursorResult has rowcount

    def update_daily_request_limit(
        self, user_id: str, api_provider: str, limit: int | None
    ) -> bool:
        with Session(self._engine) as session:
            result = session.execute(
                update(UserApiKeyRow)
                .where(UserApiKeyRow.user_id == user_id)
                .where(UserApiKeyRow.api_provider == api_provider)
                .values(daily_request_limit=limit)
            )
            session.commit()
            return result.rowcount > 0  # type: ignore[attr-defined]  # DML CursorResult has rowcount

    @staticmethod
    def _by_user_provider(user_id: str, api_provider: str):
        return (
            select(UserApiKeyRow)
            .where(UserApiKeyRow.user_id == user_id)
            .where(UserApiKeyRow.api_provider == api_provider)
        )

    @staticmethod
    def _to_record(row: UserApiKeyRow) -> ApiKeyRecord:
        return ApiKeyRecord(
            user_id=row.user_id,
            api_provider=row.api_provider,
            key_ciphertext=row.key_ciphertext,
            key_hint=row.key_hint,
            limit_usd=float(row.limit_usd),
            tracking_since=row.tracking_since,
            created_at=row.created_at,
            daily_request_limit=row.daily_request_limit,
        )
