"""Rebuild the `offer_skill` index from the scraper-owned offers (Phase 3 of the skills doc).

Reads each offer's raw skill lists, projects them onto canonical concepts with the shared
`SkillNormalizer`, and replaces the `offer_skill` rows so browsing can filter by concept in SQL.
Run via `python -m app.scripts.index_offer_skills`, e.g. after a scrape or when the alias map grows.
"""

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.application.offer_skill_index import index_entries_for_offer
from app.domain.skills import SkillNormalizer
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import OfferRow, OfferSkillRow


class PostgresOfferSkillIndexer:
    """Builds the `offer_skill` projection that lets browsing filter by canonical concept."""

    def __init__(
        self, database_or_engine: str | Engine, normalizer: SkillNormalizer
    ) -> None:
        self._engine = resolve_engine(database_or_engine)
        self._normalizer = normalizer

    def rebuild(self) -> int:
        """Recompute the whole index in one transaction (delete-all, then reinsert), returning the
        number of (offer, concept) rows written. A full rebuild is simple and always correct;
        incremental refresh keyed on `offers.scraped_at` can be layered on later if it grows large."""
        written = 0
        with Session(self._engine) as session, session.begin():
            session.execute(delete(OfferSkillRow))
            for offer_id, required, nice in session.execute(
                select(
                    OfferRow.id, OfferRow.tech_stack, OfferRow.tech_stack_nice_to_have
                )
            ):
                entries = index_entries_for_offer(
                    required or [], nice or [], self._normalizer
                )
                session.add_all(
                    OfferSkillRow(
                        offer_id=offer_id, canonical_id=canonical_id, required=req
                    )
                    for canonical_id, req in entries
                )
                written += len(entries)
        return written
