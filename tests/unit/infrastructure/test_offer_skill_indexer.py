"""Operational behavior of the offer-skill indexer, on a real (in-memory SQLite) engine:
meta stamping + freshness status, and tolerance of a not-yet-created scraper `offers` table
(a fresh deploy before the first scrape must not crash the indexer / block container start).
"""

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer
from app.infrastructure.orm_models import (
    Base,
    OfferRow,
    OfferSkillIndexMeta,
    OfferSkillRow,
)
from app.infrastructure.postgres_offer_skill_indexer import PostgresOfferSkillIndexer

_NORMALIZER = AliasMapSkillNormalizer.from_default(on_unknown=None)


def _engine_with(*models):
    # StaticPool keeps a single shared in-memory connection, so data written in one Session is
    # visible to the next (a plain in-memory SQLite engine gives each connection its own DB).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[m.__table__ for m in models])
    return engine


def _offer(offer_id: str, tech: list[str], nice: list[str] | None = None) -> OfferRow:
    return OfferRow(
        link=f"https://example.com/{offer_id}",
        id=offer_id,
        title="Dev",
        company="Acme",
        tech_stack=tech,
        description="",
        requirements="",
        benefits="",
        locations=["Remote"],
        published_date="2026-01-01",
        scraped_at=datetime.now(timezone.utc),
        portal="p",
        tech_stack_nice_to_have=nice or [],
        requirements_nice_to_have="",
        responsibilities="",
        expires="2026-12-31",
        levels=["Mid"],
        expired=False,
    )


def test_rebuild_stamps_meta_and_reports_fresh():
    engine = _engine_with(OfferRow, OfferSkillRow, OfferSkillIndexMeta)
    with Session(engine) as session, session.begin():
        session.add(_offer("o1", ["JavaScript", "k8s"], ["Postgres"]))
    indexer = PostgresOfferSkillIndexer(engine, _NORMALIZER)

    written = indexer.rebuild()

    assert written == 3  # javascript, kubernetes, postgresql
    status = indexer.status()
    assert status.built is True
    assert status.stale is False
    assert status.row_count == 3
    assert status.indexed_map_version == _NORMALIZER.map_version


def test_rebuild_is_a_noop_when_the_offers_table_is_missing():
    # Fresh deploy before the first scrape: the scraper-owned `offers` table doesn't exist.
    # Rebuild must not raise (so it can never block container start) and leaves the index unbuilt.
    engine = _engine_with(OfferSkillRow, OfferSkillIndexMeta)  # no `offers` table

    written = PostgresOfferSkillIndexer(engine, _NORMALIZER).rebuild()

    assert written == 0
    assert PostgresOfferSkillIndexer(engine, _NORMALIZER).status().built is False


def test_status_is_stale_when_built_from_a_different_map_version():
    engine = _engine_with(OfferRow, OfferSkillRow, OfferSkillIndexMeta)
    with Session(engine) as session, session.begin():
        session.add(
            OfferSkillIndexMeta(
                id=1,
                map_version="some-old-version",
                row_count=0,
                built_at=datetime.now(timezone.utc),
            )
        )

    status = PostgresOfferSkillIndexer(engine, _NORMALIZER).status()

    assert status.built is True
    assert status.stale is True
    assert status.indexed_map_version == "some-old-version"


def test_status_reports_not_built_when_meta_table_is_absent():
    # Meta table missing (migrations not yet run): status tolerates it and reports 'not built'
    # rather than raising — the failure mode that produced the original "failed to load offers".
    engine = _engine_with(OfferSkillRow)

    assert PostgresOfferSkillIndexer(engine, _NORMALIZER).status().built is False
