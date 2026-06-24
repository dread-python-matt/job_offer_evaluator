import hashlib
import json
from dataclasses import asdict
from typing import Any

from app.application.ports import AiScoreCacheRepository
from app.domain.entities import Offer, UserProfile
from app.domain.scoring import MatchScore, OfferScorer


class CachingAiScorer(OfferScorer):
    """Wraps an AI scorer with a persistent content-addressed cache, so an identical
    (model, candidate, offer) is scored by the model only once. Mirrors the inner
    scorer's sync and async APIs since the concurrent match path uses `score_async`."""

    def __init__(self, inner: Any, repository: AiScoreCacheRepository, model: str) -> None:
        self._inner = inner
        self._repository = repository
        self._model = model

    def score(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        key = self._key(candidate, offer)
        cached = self._repository.get(key)
        if cached is not None:
            return cached
        score = self._inner.score(candidate, offer)
        self._repository.put(key, score)
        return score

    async def score_async(self, candidate: UserProfile, offer: Offer) -> MatchScore:
        key = self._key(candidate, offer)
        cached = self._repository.get(key)
        if cached is not None:
            return cached
        score = await self._inner.score_async(candidate, offer)
        self._repository.put(key, score)
        return score

    def _key(self, candidate: UserProfile, offer: Offer) -> str:
        # Hash only the inputs that affect the score: the model, the full candidate,
        # and the offer fields the scorer reads (description + tech stacks).
        payload = json.dumps(
            {
                "model": self._model,
                "candidate": asdict(candidate),
                "offer": {
                    "description": offer.description,
                    "tech_stack": offer.tech_stack,
                    "tech_stack_nice_to_have": offer.tech_stack_nice_to_have,
                },
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
