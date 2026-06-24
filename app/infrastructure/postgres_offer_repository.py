from sqlalchemy import Engine, Text, cast, func, or_, select
from sqlalchemy.orm import Session

from app.application.ports import OfferRepository
from app.domain.entities import Offer
from app.domain.filters import OfferBrowseFilters
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import NormalizedSalaryRow, OfferRow, SalaryRow

# Salary sort keys -> the aggregated subquery column they order by.
_SALARY_SORT_COLUMNS = {"salary_min": "net_min", "salary_mid": "net_mid", "salary_max": "net_max"}


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
        # Salary filtering/sorting is pushed into SQL via the scraper's
        # `normalized_salary` table (precomputed NET monthly figures), so no full-table
        # load + Python pass is needed. An offer's salary is its best contract type
        # (max net_of_max across its salary rows).
        needs_salary = filters.min_salary is not None or filters.sort_by in _SALARY_SORT_COLUMNS
        salary_sq = self._best_salary_subquery() if needs_salary else None

        def apply(stmt):
            stmt = self._apply_sql_filters(stmt, filters)
            if salary_sq is not None:
                stmt = stmt.outerjoin(salary_sq, salary_sq.c.offer_id == OfferRow.id)
                if filters.min_salary is not None:
                    stmt = stmt.where(salary_sq.c.net_min >= filters.min_salary)
            return stmt

        with Session(self._engine) as session:
            total = session.scalar(
                select(func.count()).select_from(apply(select(OfferRow.id)).subquery())
            ) or 0
            data_q = (
                apply(select(OfferRow))
                .order_by(self._order_clause(filters, salary_sq))
                .limit(limit)
                .offset(offset)
            )
            rows = session.scalars(data_q).all()
            return [row.to_offer() for row in rows], total

    @staticmethod
    def _best_salary_subquery():
        """Per offer, the highest normalized NET salary on each bound across its
        contract types (its best contract on that axis)."""
        return (
            select(
                SalaryRow.offer_id.label("offer_id"),
                func.max(NormalizedSalaryRow.net_of_min).label("net_min"),
                func.max(NormalizedSalaryRow.midpoint).label("net_mid"),
                func.max(NormalizedSalaryRow.net_of_max).label("net_max"),
            )
            .join(NormalizedSalaryRow, NormalizedSalaryRow.salary_id == SalaryRow.id)
            .group_by(SalaryRow.offer_id)
            .subquery()
        )

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

    def _order_clause(self, filters: OfferBrowseFilters, salary_sq=None):
        column_name = _SALARY_SORT_COLUMNS.get(filters.sort_by)
        if column_name is not None and salary_sq is not None:
            column = salary_sq.c[column_name]
        else:
            column = OfferRow.published_date
        if filters.sort_order == "asc":
            return column.asc().nullslast()
        return column.desc().nullslast()
