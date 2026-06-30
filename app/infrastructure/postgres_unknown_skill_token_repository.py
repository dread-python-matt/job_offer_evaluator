"""Postgres-backed store of the unmapped skill-token tail (Tier-0 normalizer misses).

`replace_all` swaps in a fresh corpus snapshot in one transaction (delete-all, then reinsert), so
counts always reflect the current corpus and are never double-counted across runs — the same
"full rebuild is simple and always correct" approach as the offer-skill indexer. `top` returns the
most frequent unmapped tokens for the alias suggester / curation.
"""

from datetime import datetime, timezone

from sqlalchemy import Engine, delete, desc, select
from sqlalchemy.orm import Session

from app.application.ports import UnknownSkillToken, UnknownSkillTokenRepository
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import UnknownSkillTokenRow


class PostgresUnknownSkillTokenRepository(UnknownSkillTokenRepository):
    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)

    def replace_all(self, tokens: list[UnknownSkillToken]) -> None:
        now = datetime.now(timezone.utc)
        with Session(self._engine) as session, session.begin():
            session.execute(delete(UnknownSkillTokenRow))
            session.add_all(
                UnknownSkillTokenRow(
                    normalized=token.normalized,
                    occurrences=token.occurrences,
                    raw_samples=list(token.raw_samples),
                    updated_at=now,
                )
                for token in tokens
            )

    def top(self, limit: int = 100) -> list[UnknownSkillToken]:
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(UnknownSkillTokenRow)
                    .order_by(desc(UnknownSkillTokenRow.occurrences))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        return [
            UnknownSkillToken(
                normalized=row.normalized,
                occurrences=row.occurrences,
                raw_samples=list(row.raw_samples or []),
            )
            for row in rows
        ]
