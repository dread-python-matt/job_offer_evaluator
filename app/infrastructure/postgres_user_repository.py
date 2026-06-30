from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.application.ports import UserRepository
from app.domain.auth import User
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import UserRow


class PostgresUserRepository(UserRepository):
    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)

    def add(self, user: User) -> None:
        with Session(self._engine) as session:
            session.add(
                UserRow(
                    id=user.id,
                    email=user.email,
                    password_hash=user.password_hash,
                    token_version=user.token_version,
                    created_at=user.created_at,
                    email_verified=user.email_verified,
                )
            )
            session.commit()

    def mark_email_verified(self, user_id: str) -> None:
        with Session(self._engine) as session:
            session.execute(
                update(UserRow).where(UserRow.id == user_id).values(email_verified=True)
            )
            session.commit()

    def update_password(self, user_id: str, password_hash: str, token_version: int) -> None:
        with Session(self._engine) as session:
            session.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(password_hash=password_hash, token_version=token_version)
            )
            session.commit()

    def get_by_email(self, email: str) -> User | None:
        with Session(self._engine) as session:
            row = session.scalar(select(UserRow).where(UserRow.email == email))
            return self._to_user(row) if row is not None else None

    def get_by_id(self, user_id: str) -> User | None:
        with Session(self._engine) as session:
            row = session.get(UserRow, user_id)
            return self._to_user(row) if row is not None else None

    @staticmethod
    def _to_user(row: UserRow) -> User:
        return User(
            id=row.id,
            email=row.email,
            password_hash=row.password_hash,
            token_version=row.token_version,
            created_at=row.created_at,
            email_verified=row.email_verified,
        )
