from sqlalchemy import create_engine, select
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
            rows = session.scalars(select(OfferRow)).all()

        return [row.to_offer() for row in rows]
