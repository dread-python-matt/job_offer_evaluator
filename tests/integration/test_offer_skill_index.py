"""Integration: the `offer_skill` index makes browsing's tech filter concept-aware.

Skipped unless DATABASE_URL names a throwaway test DB (see conftest). Uses the app's own
`seed_database` to insert known `seed-*` offers, rebuilds the index, then asserts both the
projection rows and concept-based browse filtering.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATABASE_URL
from app.domain.filters import OfferBrowseFilters
from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer
from app.infrastructure.db import build_engine
from app.infrastructure.orm_models import OfferSkillIndexMeta, OfferSkillRow
from app.infrastructure.postgres_offer_repository import PostgresOfferRepository
from app.infrastructure.postgres_offer_skill_indexer import PostgresOfferSkillIndexer
from app.scripts.seed_offers import SeedOffer, seed_database

_NORMALIZER = AliasMapSkillNormalizer.from_default(on_unknown=None)


def _seed_offer(
    title: str, company: str, tech: list[str], nice: list[str]
) -> SeedOffer:
    return SeedOffer(
        title=title,
        company=company,
        portal="test.portal",
        locations=["Remote"],
        tech_stack=tech,
        tech_stack_nice_to_have=nice,
        levels=["Mid"],
        description="",
        requirements="",
        benefits="",
        responsibilities="",
        salaries=[],
        published_days_ago=1,
    )


def _engine():
    engine = build_engine(DATABASE_URL)
    # no-ops once the migrations have run
    OfferSkillRow.__table__.create(engine, checkfirst=True)
    OfferSkillIndexMeta.__table__.create(engine, checkfirst=True)
    return engine


def test_rebuild_projects_offer_skills_onto_canonical_concepts():
    engine = _engine()
    seed_database(
        engine, [_seed_offer("Dev", "IndexTest", ["JavaScript", "k8s"], ["Postgres"])]
    )

    PostgresOfferSkillIndexer(engine, _NORMALIZER).rebuild()

    with Session(engine) as session:
        rows = set(
            session.execute(
                select(OfferSkillRow.canonical_id, OfferSkillRow.required).where(
                    OfferSkillRow.offer_id == "seed-0001"
                )
            ).all()
        )
    # Aliases collapse (k8s->kubernetes, Postgres->postgresql); required wins over nice-to-have.
    assert rows == {("javascript", True), ("kubernetes", True), ("postgresql", False)}


def test_browse_tech_filter_matches_by_concept_via_index():
    engine = _engine()
    seed_database(engine, [_seed_offer("FE Dev", "IndexTest JS", ["JavaScript"], [])])
    PostgresOfferSkillIndexer(engine, _NORMALIZER).rebuild()
    repository = PostgresOfferRepository(engine, normalizer=_NORMALIZER)

    # "js" (alias) resolves to the indexed concept, so the JavaScript offer is found.
    js_results, _ = repository.browse_offers(
        OfferBrowseFilters(tech=["js"]), limit=100, offset=0
    )
    assert any(o.company == "IndexTest JS" for o in js_results)

    # A concept the offer lacks excludes it.
    py_results, _ = repository.browse_offers(
        OfferBrowseFilters(tech=["python"]), limit=100, offset=0
    )
    assert all(o.company != "IndexTest JS" for o in py_results)
