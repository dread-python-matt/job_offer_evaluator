from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.application.ports import AiScoreCacheRepository
from app.domain.scoring import AiInsight, MatchScore, ScoreComponent
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import AiScoreRow


def serialize_score(score: MatchScore) -> dict[str, Any]:
    return {
        "components": [
            {
                "name": c.name,
                "value": c.value,
                "weight": c.weight,
                "ai_insight": _insight_to_dict(c.metadata.get("ai_insight")),
            }
            for c in score.components
        ]
    }


def deserialize_score(data: dict[str, Any]) -> MatchScore:
    score = MatchScore()
    for c in data["components"]:
        insight = c.get("ai_insight")
        metadata = {"ai_insight": AiInsight(**insight)} if insight else {}
        score = score.with_component(
            ScoreComponent(name=c["name"], value=c["value"], weight=c["weight"], metadata=metadata)
        )
    return score


def _insight_to_dict(insight: AiInsight | None) -> dict[str, Any] | None:
    if insight is None:
        return None
    return {
        "rate": insight.rate,
        "pros": list(insight.pros),
        "cons": list(insight.cons),
        "rate_reason": insight.rate_reason,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresAiScoreRepository(AiScoreCacheRepository):
    def __init__(
        self,
        database_or_engine: str | Engine,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._engine = resolve_engine(database_or_engine)
        self._clock = clock

    def get(self, key: str) -> MatchScore | None:
        with Session(self._engine) as session:
            row = session.get(AiScoreRow, key)
            return deserialize_score(row.data) if row is not None else None

    def put(self, key: str, score: MatchScore) -> None:
        with Session(self._engine) as session:
            row = session.get(AiScoreRow, key)
            if row is None:
                row = AiScoreRow(key=key)
                session.add(row)
            row.data = serialize_score(score)
            row.created_at = self._clock()
            session.commit()
