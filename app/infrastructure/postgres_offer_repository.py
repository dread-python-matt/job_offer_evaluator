from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.application.ports import OfferRepository
from app.domain.entities import Offer
from app.infrastructure.orm_models import OfferRow


class PostgresOfferRepository(OfferRepository):
    """Read-only adapter over the existing `offers` table owned by the scraper."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url)

    def list_offers(self) -> list[Offer]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(OfferRow).order_by(OfferRow.published_date.desc(), OfferRow.link.asc())
            ).all()

        return [row.to_offer() for row in rows]

    def count_offers(self) -> int:
        with Session(self._engine) as session:
            return session.scalar(select(func.count()).select_from(OfferRow)) or 0
