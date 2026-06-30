"""Propose `unmapped-token → existing-canonical` aliases for human review (Phase 2, step 2).

Offline tooling, never the request path. For each unmapped token (from the corpus survey,
app/scripts/mine_skill_corpus.py) it finds the most similar canonical concept and, above a
confidence threshold, emits a suggestion for a human to approve into skill_aliases.json.

Similarity blends two signals:
  * a **lexical** score (stdlib difflib) — catches typos/spelling/separator variants; always on,
    zero dependencies; matches against both the canonical id and its label's alnum form;
  * an optional **semantic** score (embedding cosine via a `SkillEmbedder`) — catches PL/EN and
    conceptual variants that look nothing alike lexically.
The combined score is the max of the two, so embeddings only ever *add* candidates. Nothing is
auto-merged: the output is a review list, which is the guard against over-merging
(Java≠JavaScript, Go≠Golang-only, etc. stay a human call).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.domain.skills import SkillEmbedder

_DEFAULT_THRESHOLD = 0.84


@dataclass(frozen=True)
class AliasSuggestion:
    """A proposed `token -> canonical_id` mapping for review. `method` records which signal won
    ("lexical" or "semantic"); `occurrences` is the token's corpus frequency (impact ranking)."""

    token: str
    canonical_id: str
    score: float
    method: str
    occurrences: int


def _alnum(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def suggest_aliases(
    unknown_tokens: Sequence[tuple[str, int]],
    canonical_labels: Mapping[str, str],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
    embedder: SkillEmbedder | None = None,
    min_occurrences: int = 1,
) -> list[AliasSuggestion]:
    """Rank each unmapped token against the canonical concepts and return suggestions at or above
    `threshold`, most frequent (then most confident) first. `unknown_tokens` is the
    `(token, count)` tail from a corpus survey; `canonical_labels` is id→label."""
    candidates = [(t, o) for t, o in unknown_tokens if o >= min_occurrences]
    canon_ids = list(canonical_labels)
    if not candidates or not canon_ids:
        return []
    # Match each canonical on both its id and its label's alnum form ("springboot" / "Spring Boot").
    surfaces = {cid: {cid, _alnum(canonical_labels[cid])} for cid in canon_ids}

    token_vecs: dict[str, list[float]] = {}
    label_vecs: dict[str, list[float]] = {}
    if embedder is not None:
        tokens = [t for t, _ in candidates]
        token_vecs = dict(zip(tokens, embedder.embed(tokens)))
        label_vecs = dict(
            zip(canon_ids, embedder.embed([canonical_labels[c] for c in canon_ids]))
        )

    suggestions: list[AliasSuggestion] = []
    for token, occ in candidates:
        best: AliasSuggestion | None = None
        for cid in canon_ids:
            lexical = max(_ratio(token, surface) for surface in surfaces[cid])
            semantic = (
                _cosine(token_vecs[token], label_vecs[cid])
                if embedder is not None
                else 0.0
            )
            score = max(lexical, semantic)
            if best is None or score > best.score:
                method = (
                    "semantic"
                    if (embedder is not None and semantic > lexical)
                    else "lexical"
                )
                best = AliasSuggestion(token, cid, score, method, occ)
        if best is not None and best.score >= threshold:
            suggestions.append(best)
    # Most frequent first (highest-impact tokens to map), then most confident.
    suggestions.sort(key=lambda s: (s.occurrences, s.score), reverse=True)
    return suggestions


def render_suggestions(suggestions: Sequence[AliasSuggestion]) -> str:
    if not suggestions:
        return "No alias suggestions above the threshold."
    lines = [
        f"Alias suggestions for review ({len(suggestions)}) — add approved rows to "
        'skill_aliases.json "aliases":',
        f"  {'occ':>6}  {'score':>5}  {'method':<8}  token -> canonical",
    ]
    for s in suggestions:
        lines.append(
            f"  {s.occurrences:>6,}  {s.score:>5.2f}  {s.method:<8}  {s.token} -> {s.canonical_id}"
        )
    return "\n".join(lines)
