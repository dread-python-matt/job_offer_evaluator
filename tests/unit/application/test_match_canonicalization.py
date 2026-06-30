"""Integration: canonicalization at the matching boundary makes synonyms/abbreviations match,
while the original offer (display strings) is returned untouched."""

from app.application.skill_canonicalization import SkillCanonicalizer
from app.application.use_cases import MatchOffersUseCase
from app.domain.entities import Offer, Skill, UserProfile
from app.domain.filters import FilterChain, MatchCriteria
from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer
from app.infrastructure.offer_filters import SkillFilter
from app.infrastructure.scoring_strategies import SkillBasedScorer
from tests.fakes import FakeOfferRepository


def _candidate(skill: str, rating: int = 5) -> UserProfile:
    return UserProfile(
        summary="",
        skills=[Skill(name=skill, rating=rating)],
        projects=[],
        experience=[],
    )


def _match_use_case(offers, canonicalizer=None) -> MatchOffersUseCase:
    return MatchOffersUseCase(
        FakeOfferRepository(offers),
        SkillBasedScorer(),
        FilterChain([SkillFilter()]),
        canonicalizer=canonicalizer,
    )


def test_abbreviation_matches_canonical_skill_and_keeps_original_offer():
    canonicalizer = SkillCanonicalizer(
        AliasMapSkillNormalizer.from_default(on_unknown=None)
    )
    offer = Offer(link="a", title="A", company="C", tech_stack=["JavaScript"])

    results = _match_use_case([offer], canonicalizer).execute(
        MatchCriteria(candidate=_candidate("JS")), offers_limit=10
    )

    assert len(results) == 1
    assert results[0].score > 0
    assert results[0].matched_skills == {"javascript"}
    assert results[0].offer.tech_stack == [
        "JavaScript"
    ]  # original, not canonical, for display


def test_without_canonicalizer_the_abbreviation_does_not_match():
    # Baseline: literal matching misses "JS" vs "JavaScript", so the offer is filtered out.
    offer = Offer(link="a", title="A", company="C", tech_stack=["JavaScript"])

    results = _match_use_case([offer]).execute(
        MatchCriteria(candidate=_candidate("JS"), min_score=0.01), offers_limit=10
    )

    assert results == []
