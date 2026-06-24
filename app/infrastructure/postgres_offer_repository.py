from sqlalchemy import Engine, Text, cast, func, or_, select
from sqlalchemy.orm import Session

from app.application.ports import OfferRepository
from app.domain.entities import Offer
from app.domain.filters import OfferBrowseFilters, salary_meets_minimum
from app.domain.sorting import sort_offers
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import OfferRow


class PostgresOfferRepository(OfferRepository):
    """Read-only adapter over the existing `offers` table owned by the scraper."""

    def __init__(self, database_or_engine: str | Engine) -> None:
        self._engine = resolve_engine(database_or_engine)

    def list_offers(self) -> list[Offer]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(OfferRow).order_by(OfferRow.published_date.desc(), OfferRow.link.asc())
            ).all()

        return [row.to_offer() for row in rows]

    def count_offers(self) -> int:
        with Session(self._engine) as session:
            return session.scalar(select(func.count()).select_from(OfferRow)) or 0

    def browse_offers(
        self, filters: OfferBrowseFilters, limit: int, offset: int
    ) -> tuple[list[Offer], int]:
        with Session(self._engine) as session:
            needs_python = filters.min_salary is not None or filters.sort_by == "salary"
            base_q = self._apply_sql_filters(select(OfferRow), filters)

            if needs_python:
                rows = session.scalars(base_q).all()
                offers = [row.to_offer() for row in rows]
                if filters.min_salary is not None:
                    offers = [o for o in offers if salary_meets_minimum(o, filters.min_salary)]
                offers = sort_offers(offers, filters.sort_by, filters.sort_order)
                total = len(offers)
                return offers[offset : offset + limit], total

            count_q = self._apply_sql_filters(
                select(func.count()).select_from(OfferRow), filters
            )
            total = session.scalar(count_q) or 0
            data_q = (
                base_q
                .order_by(self._order_clause(filters))
                .limit(limit)
                .offset(offset)
            )
            rows = session.scalars(data_q).all()
            return [row.to_offer() for row in rows], total

    def _apply_sql_filters(self, query, filters: OfferBrowseFilters):
        if not filters.include_expired:
            query = query.where(OfferRow.expired == False)  # noqa: E712
        if filters.search:
            term = f"%{filters.search.lower()}%"
            query = query.where(
                or_(
                    func.lower(OfferRow.title).like(term),
                    func.lower(OfferRow.company).like(term),
                )
            )
        if filters.location:
            query = query.where(
                func.lower(cast(OfferRow.locations, Text)).like(
                    f"%{filters.location.lower()}%"
                )
            )
        if filters.level:
            level_conds = [
                func.lower(cast(OfferRow.levels, Text)).like(f'%"{level.lower()}"%')
                for level in filters.level
            ]
            query = query.where(or_(*level_conds))
        if filters.tech:
            for tech in filters.tech:
                pattern = f"%{tech.lower()}%"
                query = query.where(
                    or_(
                        func.lower(cast(OfferRow.tech_stack, Text)).like(pattern),
                        func.lower(cast(OfferRow.tech_stack_nice_to_have, Text)).like(pattern),
                    )
                )
        return query

    def _order_clause(self, filters: OfferBrowseFilters):
        if filters.sort_order == "asc":
            return OfferRow.published_date.asc().nullslast()
        return OfferRow.published_date.desc().nullslast()
