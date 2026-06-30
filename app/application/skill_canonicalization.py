"""Rewrite a candidate profile and offers so their skill tokens are canonical concepts.

Applied at the matching boundary (in the use cases) on **scoring-only copies**, so the
existing comparison logic (`skill_utils`, the filters, `matched_skills`) operates on concepts
rather than literal strings while the originals — and the strings shown to the user — are
untouched. With no normalizer it is a no-op, so callers/tests that don't wire one keep exact
literal behavior.
"""

from dataclasses import replace

from app.domain.entities import Offer, UserProfile
from app.domain.skills import SkillNormalizer


class SkillCanonicalizer:
    def __init__(self, normalizer: SkillNormalizer | None = None) -> None:
        self._normalizer = normalizer

    def _canon(self, raw: str) -> str:
        assert self._normalizer is not None  # callers guard the None case before reaching here
        return self._normalizer.normalize(raw).id

    def _canon_all(self, raws: list[str]) -> list[str]:
        # Map each token in place (no de-dup): length is preserved, so the weighted-ratio
        # denominator is unchanged and duplicates collapse to the same id harmlessly.
        return [self._canon(r) for r in raws]

    def canonicalize_candidate(self, candidate: UserProfile) -> UserProfile:
        if self._normalizer is None:
            return candidate
        return replace(
            candidate,
            skills=[replace(s, name=self._canon(s.name)) for s in candidate.skills],
            projects=[
                replace(p, tech_stack=self._canon_all(p.tech_stack))
                for p in candidate.projects
            ],
            experience=[
                replace(e, tech_stack=self._canon_all(e.tech_stack))
                for e in candidate.experience
            ],
        )

    def canonicalize_offer(self, offer: Offer) -> Offer:
        if self._normalizer is None:
            return offer
        return replace(
            offer,
            tech_stack=self._canon_all(offer.tech_stack),
            tech_stack_nice_to_have=self._canon_all(offer.tech_stack_nice_to_have),
        )
