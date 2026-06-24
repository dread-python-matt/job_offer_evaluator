import asyncio

from app.application.ports import AiScoreCacheRepository
from app.domain.entities import Offer, Skill, UserProfile
from app.domain.scoring import MatchScore, OfferScorer, ScoreComponent
from app.infrastructure.caching_ai_scorer import CachingAiScorer


class InMemoryAiScoreRepository(AiScoreCacheRepository):
    def __init__(self) -> None:
        self.store: dict[str, MatchScore] = {}

    def get(self, key: str) -> MatchScore | None:
        return self.store.get(key)

    def put(self, key: str, score: MatchScore) -> None:
        self.store[key] = score


class CountingScorer(OfferScorer):
    def __init__(self) -> None:
        self.calls = 0

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        self.calls += 1
        return MatchScore().with_component(ScoreComponent(name="description", value=0.8, weight=1.0))

    async def score_async(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        return self.score(candidate, offer)


def _candidate() -> UserProfile:
    return UserProfile(summary="dev", skills=[Skill(name="Python", rating=5)], projects=[], experience=[])


def _offer(link: str = "a", description: str = "desc") -> Offer:
    return Offer(link=link, title="A", company="C", tech_stack=["Python"], description=description)


def test_second_score_of_same_inputs_is_served_from_cache():
    inner = CountingScorer()
    scorer = CachingAiScorer(inner, InMemoryAiScoreRepository(), model="gpt-4o")

    first = scorer.score(_candidate(), _offer())
    second = scorer.score(_candidate(), _offer())

    assert inner.calls == 1
    assert second.get("description") == first.get("description")


def test_different_offer_content_misses_the_cache():
    inner = CountingScorer()
    scorer = CachingAiScorer(inner, InMemoryAiScoreRepository(), model="gpt-4o")

    scorer.score(_candidate(), _offer(description="one"))
    scorer.score(_candidate(), _offer(description="two"))

    assert inner.calls == 2


def test_different_model_misses_the_cache():
    repo = InMemoryAiScoreRepository()
    CachingAiScorer(CountingScorer(), repo, model="gpt-4o").score(_candidate(), _offer())
    inner = CountingScorer()

    CachingAiScorer(inner, repo, model="gemini-2.5-flash").score(_candidate(), _offer())

    assert inner.calls == 1  # not served from the gpt-4o entry


def test_async_path_also_caches():
    inner = CountingScorer()
    scorer = CachingAiScorer(inner, InMemoryAiScoreRepository(), model="gpt-4o")

    asyncio.run(scorer.score_async(_candidate(), _offer()))
    asyncio.run(scorer.score_async(_candidate(), _offer()))

    assert inner.calls == 1
