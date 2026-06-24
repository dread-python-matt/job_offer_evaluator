from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.application.ports import UserProfileRepository
from app.domain.entities import Experience, Project, Skill, UserProfile
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import Base, UserProfileRow


def profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    return {
        "summary": profile.summary,
        "skills": [{"name": s.name, "rating": s.rating} for s in profile.skills],
        "projects": [
            {
                "name": p.name,
                "repository_link": p.repository_link,
                "summary": p.summary,
                "date_from": p.date_from,
                "date_to": p.date_to,
                "tech_stack": list(p.tech_stack),
            }
            for p in profile.projects
        ],
        "experience": [
            {
                "title": e.title,
                "company": e.company,
                "description": e.description,
                "date_from": e.date_from,
                "date_to": e.date_to,
                "tech_stack": list(e.tech_stack),
            }
            for e in profile.experience
        ],
    }


def profile_from_dict(data: dict[str, Any]) -> UserProfile:
    return UserProfile(
        summary=data["summary"],
        skills=[Skill(name=s["name"], rating=s["rating"]) for s in data["skills"]],
        projects=[Project(**p) for p in data["projects"]],
        experience=[Experience(**e) for e in data["experience"]],
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresUserProfileRepository(UserProfileRepository):
    """Stores each user's profile as a JSON document, one row per user (keyed by user_id)."""

    def __init__(
        self,
        database_or_engine: str | Engine,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._engine = resolve_engine(database_or_engine)
        Base.metadata.create_all(self._engine, tables=[UserProfileRow.__table__])
        self._clock = clock

    def save(self, user_id: str, profile: UserProfile) -> None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(UserProfileRow).where(UserProfileRow.user_id == user_id)
            )
            if row is None:
                row = UserProfileRow(user_id=user_id)
                session.add(row)
            row.data = profile_to_dict(profile)
            row.updated_at = self._clock()
            session.commit()

    def load(self, user_id: str) -> UserProfile | None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(UserProfileRow).where(UserProfileRow.user_id == user_id)
            )
            return profile_from_dict(row.data) if row is not None else None
