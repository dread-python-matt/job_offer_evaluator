"""Canonical skill concept + the normalizer port that produces it.

Skill strings arrive in many surface forms — "JS"/"JavaScript", "k8s"/"Kubernetes",
"node.js"/"nodejs", PL/EN variants, mixed case and Polish diacritics. Comparing them
literally makes every downstream number (skill ratio, the cheap pre-filter, AI pre-ranking)
inherit string-match errors. A `SkillNormalizer` collapses each raw token to ONE canonical
concept, so comparison happens on concepts rather than spellings.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalSkill:
    """A raw skill token resolved to a canonical concept.

    `id` is a stable lowercase slug (e.g. "javascript"); equal ids mean "same skill". For an
    unrecognized token the id is its normalized surface form (so matching still degrades to a
    cleaned-up literal compare). `confidence` is 1.0 for a deterministic resolution (an alias
    hit, or a token already in canonical form); a future semantic/fuzzy fallback may resolve at
    `<1.0` so low-confidence matches can be down-weighted. `source` records how it resolved,
    for auditing."""

    id: str
    confidence: float = 1.0
    source: str = "passthrough"


class SkillNormalizer(ABC):
    """Port: map a raw skill token to its `CanonicalSkill`. Deterministic and side-effect-light
    in the request path (an implementation may log unknown tokens). Adapters live in
    infrastructure."""

    @abstractmethod
    def normalize(self, raw: str) -> CanonicalSkill: ...

    @property
    def map_version(self) -> str:
        """Version identifier of the normalization ruleset, so a derived cache (e.g. the
        offer-skill index) can detect it was built from an older ruleset and is stale. Defaults
        to "unknown"; an adapter backed by a versioned resource (the alias map) overrides it."""
        return "unknown"


class SkillEmbedder(ABC):
    """Port: embed text into vectors for semantic similarity. Used only by offline tooling
    (the alias suggester), never the request path; adapters live in infrastructure."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...
