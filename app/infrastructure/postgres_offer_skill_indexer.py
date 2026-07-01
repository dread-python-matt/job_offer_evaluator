"""Rebuild and inspect the `offer_skill` index (Phase 3 of the skills doc).

Reads each offer's raw skill lists, projects them onto canonical concepts with the shared
`SkillNormalizer`, and replaces the `offer_skill` rows so browsing can filter by concept in SQL.
Each rebuild also stamps `offer_skill_index_meta` with the alias-map version, time, and row count,
so a stale index (the map changed but the indexer wasn't re-run) is observable rather than silent.
Run via `python -m app.scripts.index_offer_skills` - e.g. after new offers are loaded or when the map grows.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.orm import Session

from app.application.offer_skill_index import index_entries_for_offer
from app.domain.skills import SkillNormalizer
from app.infrastructure.db import resolve_engine
from app.infrastructure.orm_models import OfferRow, OfferSkillIndexMeta, OfferSkillRow

_logger = logging.getLogger("app.skills")

_META_ID = 1  # fixed sentinel for the single-row meta table


@dataclass(frozen=True)
class OfferSkillIndexStatus:
    """Freshness of the persisted `offer_skill` index relative to the current alias map.
    `stale` is true when the index was never built OR was built from a different map version."""

    built: bool
    stale: bool
    current_map_version: str
    indexed_map_version: str | None = None
    row_count: int | None = None
    built_at: datetime | None = None

    def describe(self) -> str:
        """One-line human summary for the CLI / deploy logs."""
        if not self.built:
            return (
                "offer_skill index: NOT BUILT - browsing's tech filter will match nothing. "
                "Run `python -m app.scripts.index_offer_skills`."
            )
        if self.stale:
            return (
                f"offer_skill index: STALE - {self.row_count} rows built from map "
                f"{self.indexed_map_version!r}, but the current map is "
                f"{self.current_map_version!r}. Re-run the indexer."
            )
        return (
            f"offer_skill index: fresh - {self.row_count} rows, map "
            f"{self.indexed_map_version!r}, built at {self.built_at}."
        )


class PostgresOfferSkillIndexer:
    """Builds and inspects the `offer_skill` projection that lets browsing filter by concept."""

    def __init__(
        self, database_or_engine: str | Engine, normalizer: SkillNormalizer
    ) -> None:
        self._engine = resolve_engine(database_or_engine)
        self._normalizer = normalizer

    def rebuild(self) -> int:
        """Recompute the whole index in one transaction (delete-all, reinsert) and stamp the meta
        row, returning the number of (offer, concept) rows written. A full rebuild is simple and
        always correct; incremental refresh keyed on `offers.scraped_at` can be layered on later.

        If the externally-owned `offers` table doesn't exist yet (a fresh deploy before any
        offers are loaded), there is nothing to project: log and leave the existing index untouched, returning
        0, so this can run unconditionally at startup without ever blocking boot."""
        if not inspect(self._engine).has_table(OfferRow.__tablename__):
            _logger.warning(
                "offer_skill index rebuild skipped: the externally-owned 'offers' table does "
                "not exist yet",
                extra={"event": "offer_skill_index_skipped"},
            )
            return 0
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
            # Stamp bookkeeping in the same transaction so meta never disagrees with the index.
            session.execute(delete(OfferSkillIndexMeta))
            session.add(
                OfferSkillIndexMeta(
                    id=_META_ID,
                    map_version=self._normalizer.map_version,
                    row_count=written,
                    built_at=datetime.now(timezone.utc),
                )
            )
        return written

    def status(self) -> OfferSkillIndexStatus:
        """Report whether the index is built and whether it is stale w.r.t. the current alias map.
        Tolerates a not-yet-migrated database (missing meta table) by reporting 'not built'."""
        current = self._normalizer.map_version
        if not inspect(self._engine).has_table(OfferSkillIndexMeta.__tablename__):
            return OfferSkillIndexStatus(
                built=False, stale=True, current_map_version=current
            )
        with Session(self._engine) as session:
            meta = session.get(OfferSkillIndexMeta, _META_ID)
        if meta is None:
            return OfferSkillIndexStatus(
                built=False, stale=True, current_map_version=current
            )
        return OfferSkillIndexStatus(
            built=True,
            stale=meta.map_version != current,
            current_map_version=current,
            indexed_map_version=meta.map_version,
            row_count=meta.row_count,
            built_at=meta.built_at,
        )
