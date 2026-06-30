"""Project an offer's raw skill lists onto canonical concepts for the searchable index.

Pure core of the offer-skill index (Phase 3 of docs/skills-normalization.md). Browsing's "tech"
filter can't match concepts directly because the offers table stores raw scraper strings; this
maps each offer's `tech_stack` / `tech_stack_nice_to_have` to canonical ids — via the SAME
`SkillNormalizer` the matching path uses — so the projection can be persisted and filtered in SQL.
"""

from app.domain.skills import SkillNormalizer


def index_entries_for_offer(
    required: list[str], nice_to_have: list[str], normalizer: SkillNormalizer
) -> list[tuple[str, bool]]:
    """Deduped canonical `(id, is_required)` entries for one offer. A concept that appears in the
    required stack is marked required, taking precedence over a nice-to-have occurrence of the
    same concept; blank tokens (which normalize to an empty id) are dropped."""
    by_id: dict[str, bool] = {}
    for raw in required:
        canonical_id = normalizer.normalize(raw).id
        if canonical_id:
            by_id[canonical_id] = True
    for raw in nice_to_have:
        canonical_id = normalizer.normalize(raw).id
        if canonical_id and canonical_id not in by_id:
            by_id[canonical_id] = False
    return list(by_id.items())
