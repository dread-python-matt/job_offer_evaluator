from sqlalchemy import Engine, Text, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from app.application.ports import OfferRepository
from app.domain.entities import Offer
from app.domain.filters import MatchCriteria, OfferBrowseFilters
from app.domain.skills import SkillNormalizer
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import (
    NormalizedSalaryRow,
    OfferRow,
    OfferSkillRow,
    SalaryRow,
)

# Salary sort keys -> the aggregated subquery column they order by.
_SALARY_SORT_COLUMNS = {
    "salary_min": "net_min",
    "salary_mid": "net_mid",
    "salary_max": "net_max",
}


class PostgresOfferRepository(OfferRepository):
    """Read-only adapter over the existing `offers` table owned by the scraper."""

    def __init__(
        self,
        database_or_engine: str | Engine,
        normalizer: SkillNormalizer | None = None,
    ) -> None:
        self._engine = resolve_engine(database_or_engine)
        # When set, the browse "tech" filter matches canonical concepts via the offer_skill index
        # (so "k8s" finds offers tagged "Kubernetes"); when None it falls back to raw substring
        # matching on the stored stacks. The index is built by app.scripts.index_offer_skills with
        # this same normalizer, so the query side and the stored side agree on concepts.
        self._normalizer = normalizer

    def candidate_offers(self, criteria: MatchCriteria) -> list[Offer]:
        # A match filters on the same structural fields as browsing (location, net-salary
        # floor, expired, level), so reuse the exact SQL machinery — only matching rows are
        # loaded instead of the whole table. tech/search/sort don't apply: skill relevance
        # is scored (not filtered) and the use case sorts the final results.
        filters = OfferBrowseFilters(
            location=criteria.location,
            min_salary=criteria.min_salary,
            include_expired=criteria.include_expired,
            level=criteria.level,
        )
        salary_sq = self._salary_subquery_if_needed(filters)
        stmt = self._apply_filters(select(OfferRow), filters, salary_sq)
        with Session(self._engine) as session:
            return [row.to_offer() for row in session.scalars(stmt).all()]

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
        salary_sq = self._salary_subquery_if_needed(filters)
        with Session(self._engine) as session:
            total = (
                session.scalar(
                    select(func.count()).select_from(
                        self._apply_filters(
                            select(OfferRow.id), filters, salary_sq
                        ).subquery()
                    )
                )
                or 0
            )
            data_q = (
                self._apply_filters(select(OfferRow), filters, salary_sq)
                .order_by(self._order_clause(filters, salary_sq))
                .limit(limit)
                .offset(offset)
            )
            rows = session.scalars(data_q).all()
            return [row.to_offer() for row in rows], total

    def _salary_subquery_if_needed(self, filters: OfferBrowseFilters):
        """The best-salary subquery, but only when the request needs it (a min-salary floor
        or a salary sort) — otherwise None, so no join is added."""
        needs_salary = (
            filters.min_salary is not None or filters.sort_by in _SALARY_SORT_COLUMNS
        )
        return self._best_salary_subquery() if needs_salary else None

    def _apply_filters(self, stmt, filters: OfferBrowseFilters, salary_sq):
        """Apply the structural filters and (when present) the salary-floor join shared by
        browsing and matching, so both express identical filter semantics in SQL."""
        stmt = self._apply_sql_filters(stmt, filters)
        if salary_sq is not None:
            stmt = stmt.outerjoin(salary_sq, salary_sq.c.offer_id == OfferRow.id)
            if filters.min_salary is not None:
                stmt = stmt.where(salary_sq.c.net_min >= filters.min_salary)
        return stmt

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
            query = self._apply_tech_filter(query, filters.tech)
        return query

    def _apply_tech_filter(self, query, techs: list[str]):
        """Filter to offers having ALL requested techs. With a normalizer wired, each term is
        canonicalized and matched against the `offer_skill` index (concept-based, so "k8s" finds
        "Kubernetes"); without one, fall back to raw substring matching on the stored stacks."""
        if self._normalizer is None:
            for tech in techs:
                pattern = f"%{tech.lower()}%"
                query = query.where(
                    or_(
                        func.lower(cast(OfferRow.tech_stack, Text)).like(pattern),
                        func.lower(cast(OfferRow.tech_stack_nice_to_have, Text)).like(
                            pattern
                        ),
                    )
                )
            return query
        for tech in techs:
            canonical_id = self._normalizer.normalize(tech).id
            if not canonical_id:
                continue
            query = query.where(
                exists(
                    select(OfferSkillRow.offer_id)
                    .where(OfferSkillRow.offer_id == OfferRow.id)
                    .where(OfferSkillRow.canonical_id == canonical_id)
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
