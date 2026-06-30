from collections import Counter

from app.application.skill_corpus import (
    collect_unknown_tokens,
    render_coverage,
    summarize_skill_corpus,
)
from app.domain.skills import CanonicalSkill, SkillNormalizer


class _FakeNormalizer(SkillNormalizer):
    """Recognizes the given (lowercased) tokens; everything else passes through as unknown."""

    def __init__(self, recognized: set[str]) -> None:
        self._recognized = recognized

    def normalize(self, raw: str) -> CanonicalSkill:
        key = raw.strip().lower()
        source = "canonical" if key in self._recognized else "passthrough"
        return CanonicalSkill(id=key, source=source)


def test_summarize_counts_occurrences_and_coverage():
    counts = Counter({"Python": 10, "Java": 4, "CobolX": 3, "cobolx": 1})

    report = summarize_skill_corpus(counts, _FakeNormalizer({"python", "java"}))

    assert report.total_occurrences == 18
    assert report.recognized_occurrences == 14
    assert report.recognized_ratio == 14 / 18
    assert report.distinct_tokens == 4


def test_summarize_merges_unknown_spelling_variants_and_sorts_by_frequency():
    counts = Counter({"CobolX": 3, "cobolx": 1, "Whitespace": 5})

    report = summarize_skill_corpus(counts, _FakeNormalizer(set()))

    # "CobolX" and "cobolx" both normalize to "cobolx" -> merged to 4; ordered by frequency.
    assert report.unknown_by_frequency == [("whitespace", 5), ("cobolx", 4)]
    assert report.distinct_unknown == 2


def test_render_includes_coverage_and_unmapped_tokens():
    report = summarize_skill_corpus(
        Counter({"Python": 9, "Rustacean": 1}), _FakeNormalizer({"python"})
    )

    out = render_coverage(report, top=10)

    assert "recognized 9 / 10" in out
    assert "90.0%" in out
    assert "rustacean" in out


def test_render_handles_full_coverage_without_listing_tokens():
    report = summarize_skill_corpus(Counter({"Python": 3}), _FakeNormalizer({"python"}))

    out = render_coverage(report, top=10)

    assert "100.0%" in out
    assert "(unmapped: 0)" in out


def test_collect_unknown_tokens_ranks_by_frequency_with_raw_samples():
    counts = Counter({"CobolX": 3, "cobolx": 1, "Python": 9, "Whitespace": 5})

    tokens = collect_unknown_tokens(counts, _FakeNormalizer({"python"}))

    # Python is recognized (excluded); "CobolX"/"cobolx" merge to normalized "cobolx" (4).
    assert [(t.normalized, t.occurrences) for t in tokens] == [
        ("whitespace", 5),
        ("cobolx", 4),
    ]
    cobolx = next(t for t in tokens if t.normalized == "cobolx")
    assert set(cobolx.raw_samples) == {"CobolX", "cobolx"}


class _ConstNormalizer(SkillNormalizer):
    """Every token is an unknown passthrough under one shared id, to exercise sample-capping."""

    def normalize(self, raw: str) -> CanonicalSkill:
        return CanonicalSkill(id="x", source="passthrough")


def test_collect_unknown_tokens_caps_raw_samples():
    counts = Counter({f"raw{i}": 1 for i in range(10)})

    tokens = collect_unknown_tokens(counts, _ConstNormalizer(), max_samples=3)

    assert len(tokens) == 1
    assert tokens[0].occurrences == 10  # all 10 raw tokens merged under one id
    assert len(tokens[0].raw_samples) == 3  # samples capped
