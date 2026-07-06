"""Survey skill tokens against the canonical map: how many resolve, and which don't.

Pure core for the `mine_skill_corpus` script:
feed it a frequency count of raw skill tokens and a `SkillNormalizer`, and it reports canonical
coverage plus the unmapped tail ranked by frequency — the highest-ROI entries to add to the
alias map next.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from app.application.ports import UnknownSkillToken
from app.domain.skills import SkillNormalizer


@dataclass(frozen=True)
class CorpusCoverage:
    total_occurrences: int
    distinct_tokens: int
    recognized_occurrences: int
    # (normalized id, occurrences), most frequent first — what to add to the map next.
    unknown_by_frequency: list[tuple[str, int]]

    @property
    def recognized_ratio(self) -> float:
        return (
            self.recognized_occurrences / self.total_occurrences if self.total_occurrences else 0.0
        )

    @property
    def distinct_unknown(self) -> int:
        return len(self.unknown_by_frequency)


def summarize_skill_corpus(
    token_counts: Mapping[str, int], normalizer: SkillNormalizer
) -> CorpusCoverage:
    """Classify each raw token via the normalizer. A token resolved to an alias/canonical
    concept counts as recognized; an unrecognized one is tallied (by its normalized surface
    form, so spelling variants of the same unknown merge) into the unmapped tail."""
    total = 0
    recognized = 0
    unknown: Counter[str] = Counter()
    for raw, count in token_counts.items():
        total += count
        result = normalizer.normalize(raw)
        if result.source == "passthrough":
            unknown[result.id] += count
        else:
            recognized += count
    return CorpusCoverage(
        total_occurrences=total,
        distinct_tokens=len(token_counts),
        recognized_occurrences=recognized,
        unknown_by_frequency=unknown.most_common(),
    )


def collect_unknown_tokens(
    token_counts: Mapping[str, int],
    normalizer: SkillNormalizer,
    *,
    max_samples: int = 5,
) -> list[UnknownSkillToken]:
    """The unmapped (Tier-0 miss) tail as persistable records: each normalized token with its
    total occurrences and up to `max_samples` example raw forms, most frequent first. Mirrors
    `summarize_skill_corpus`'s classification (a `passthrough` result is unknown) while keeping
    a few raw samples for human review."""
    occurrences: Counter[str] = Counter()
    samples: dict[str, list[str]] = {}
    for raw, count in token_counts.items():
        result = normalizer.normalize(raw)
        if result.source != "passthrough":
            continue
        occurrences[result.id] += count
        bucket = samples.setdefault(result.id, [])
        if raw not in bucket and len(bucket) < max_samples:
            bucket.append(raw)
    return [
        UnknownSkillToken(normalized=token, occurrences=count, raw_samples=samples[token])
        for token, count in occurrences.most_common()
    ]


def render_coverage(report: CorpusCoverage, *, top: int = 50) -> str:
    lines = [
        "Skill corpus coverage",
        f"  occurrences: recognized {report.recognized_occurrences:,} / "
        f"{report.total_occurrences:,} ({report.recognized_ratio:.1%})",
        f"  distinct tokens: {report.distinct_tokens:,}  (unmapped: {report.distinct_unknown:,})",
    ]
    if report.unknown_by_frequency:
        lines += [
            "",
            f"Top {min(top, report.distinct_unknown)} unmapped tokens (add to skill_aliases.json):",
        ]
        lines += [f"  {count:>6,}  {token}" for token, count in report.unknown_by_frequency[:top]]
    return "\n".join(lines)
