from app.application.offer_skill_index import index_entries_for_offer
from app.domain.skills import CanonicalSkill, SkillNormalizer


class _FakeNormalizer(SkillNormalizer):
    """Collapses a few known surface forms to canonical ids; unknown -> casefolded; blank -> ''."""

    _MAP = {"js": "javascript", "javascript": "javascript", "k8s": "kubernetes"}

    def normalize(self, raw: str) -> CanonicalSkill:
        key = raw.strip().casefold()
        return CanonicalSkill(id=self._MAP.get(key, key))


def test_collapses_aliases_and_dedups_within_required():
    assert index_entries_for_offer(["JS", "JavaScript"], [], _FakeNormalizer()) == [
        ("javascript", True)
    ]


def test_required_takes_precedence_over_nice_to_have():
    assert index_entries_for_offer(["JS"], ["js"], _FakeNormalizer()) == [
        ("javascript", True)
    ]


def test_nice_to_have_only_is_marked_not_required():
    assert index_entries_for_offer([], ["k8s"], _FakeNormalizer()) == [
        ("kubernetes", False)
    ]


def test_blank_tokens_are_dropped():
    assert index_entries_for_offer(["", "JS"], ["  "], _FakeNormalizer()) == [
        ("javascript", True)
    ]


def test_empty_offer_yields_no_entries():
    assert index_entries_for_offer([], [], _FakeNormalizer()) == []
