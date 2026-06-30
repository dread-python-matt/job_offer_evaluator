"""Deterministic, dependency-free skill normalizer (Tier 0).

Pipeline per token: fold case + diacritics → collapse separators (except for `protected`
tokens, where punctuation is meaningful) → alias→canonical lookup. A token already in canonical
form resolves to itself; anything unrecognized passes through as its cleaned surface form and is
recorded via the unknown sink (default: a structured log on `app.skills`) so the map can be grown
from real corpus tokens. Pure dict lookups — microseconds — so it is safe in the request path.
"""

import json
import logging
import unicodedata
from collections.abc import Callable
from pathlib import Path

from app.domain.skills import CanonicalSkill, SkillNormalizer

_logger = logging.getLogger("app.skills")

_DEFAULT_MAP_PATH = Path(__file__).resolve().parent / "data" / "skill_aliases.json"

# Separators stripped when collapsing a token (so "node.js"/"node js"/"node-js" → "nodejs").
# "+" and "#" are intentionally NOT separators, so "c++"/"c#"/"f#" survive without protection.
_SEPARATORS = frozenset(" \t\n.-_/")

# Polish (+ a few common Latin) diacritics. NFKD does not decompose "ł", so it needs an explicit
# entry; the NFKD pass afterwards catches accented forms not listed here.
_DIACRITIC_FOLD = str.maketrans(
    {
        "ł": "l",
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
        "ß": "ss",
    }
)

# (raw_token, normalized_key) -> None. Default sink logs structured events for observability.
UnknownSink = Callable[[str, str], None]

# Each distinct unknown token is logged once per process; a token reappears on every match
# request, so without this a single unmapped skill would flood the logs. The set is bounded by
# the (small) skill vocabulary. Phase 2 replaces this with a counting table (see the design doc).
_seen_unknown: set[str] = set()


def log_unknown_skill_token(raw: str, normalized: str) -> None:
    if normalized in _seen_unknown:
        return
    _seen_unknown.add(normalized)
    _logger.info(
        "unknown skill token",
        extra={"event": "unknown_skill_token", "raw": raw, "normalized": normalized},
    )


def _fold(raw: str) -> str:
    folded = raw.strip().casefold().translate(_DIACRITIC_FOLD)
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


class AliasMapSkillNormalizer(SkillNormalizer):
    def __init__(
        self, spec: dict, on_unknown: UnknownSink | None = log_unknown_skill_token
    ) -> None:
        # id -> display label, kept so tooling (the alias suggester) can match unmapped tokens
        # against canonical labels, not just ids. Membership checks use the dict's keys.
        self._canonical: dict[str, str] = {
            cid: (meta or {}).get("label", cid)
            for cid, meta in spec.get("canonical", {}).items()
        }
        # Build protected first: its members bypass separator collapsing, both for incoming
        # tokens and when normalizing alias keys, so they line up.
        self._protected: set[str] = {_fold(t) for t in spec.get("protected", [])}
        self._aliases: dict[str, str] = {
            self._lookup_key(alias): canonical
            for alias, canonical in spec.get("aliases", {}).items()
        }
        self._never_merge: list[tuple[str, str]] = [
            tuple(pair) for pair in spec.get("never_merge", [])
        ]
        self._on_unknown = on_unknown

    @classmethod
    def from_default(
        cls, on_unknown: UnknownSink | None = log_unknown_skill_token
    ) -> "AliasMapSkillNormalizer":
        spec = json.loads(_DEFAULT_MAP_PATH.read_text(encoding="utf-8"))
        return cls(spec, on_unknown=on_unknown)

    def _lookup_key(self, raw: str) -> str:
        folded = _fold(raw)
        if folded in self._protected:
            return folded
        return "".join(ch for ch in folded if ch not in _SEPARATORS)

    def normalize(self, raw: str) -> CanonicalSkill:
        key = self._lookup_key(raw)
        if not key:
            return CanonicalSkill(id="", source="passthrough")
        canonical = self._aliases.get(key)
        if canonical is not None:
            return CanonicalSkill(id=canonical, source="alias")
        if key in self._canonical:
            return CanonicalSkill(id=key, source="canonical")
        if self._on_unknown is not None:
            self._on_unknown(raw, key)
        return CanonicalSkill(id=key, source="passthrough")

    @property
    def never_merge_pairs(self) -> list[tuple[str, str]]:
        """Canonical-id pairs that must never resolve to the same concept (asserted by tests)."""
        return list(self._never_merge)

    @property
    def canonical_labels(self) -> dict[str, str]:
        """Canonical id → display label, for tooling (e.g. the alias suggester)."""
        return dict(self._canonical)
