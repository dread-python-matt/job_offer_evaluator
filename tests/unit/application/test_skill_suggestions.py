from app.application.skill_suggestions import (
    AliasSuggestion,
    render_suggestions,
    suggest_aliases,
)
from app.domain.skills import SkillEmbedder

CANON = {
    "javascript": "JavaScript",
    "kubernetes": "Kubernetes",
    "oop": "Object Oriented Programming",
}


class _FakeEmbedder(SkillEmbedder):
    """Returns a preset vector per text; records what it was asked to embed."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vectors[t] for t in texts]


def test_lexical_typo_is_suggested():
    out = suggest_aliases([("javascrpit", 7)], CANON, min_occurrences=1)
    assert len(out) == 1
    suggestion = out[0]
    assert suggestion.canonical_id == "javascript"
    assert suggestion.method == "lexical"
    assert suggestion.occurrences == 7
    assert suggestion.score >= 0.84


def test_unrelated_token_is_not_suggested():
    assert (
        suggest_aliases(
            [("rustlang", 9)], {"javascript": "JavaScript"}, min_occurrences=1
        )
        == []
    )


def test_min_occurrences_filters_rare_tokens():
    assert suggest_aliases([("javascrpit", 1)], CANON, min_occurrences=2) == []


def test_suggestions_sorted_by_occurrences_then_score():
    out = suggest_aliases(
        [("javascrip", 2), ("javascripts", 10)],
        {"javascript": "JavaScript"},
        min_occurrences=1,
    )
    assert [s.occurrences for s in out] == [10, 2]


def test_embedder_enables_a_semantic_match_lexical_would_miss():
    # Polish for OOP: lexically far from "oop"/"objectorientedprogramming", but embeds identically.
    token = "programowanieobiektowe"
    vectors = {token: [1.0, 0.0], "Object Oriented Programming": [1.0, 0.0]}
    embedder = _FakeEmbedder(vectors)

    out = suggest_aliases(
        [(token, 4)],
        {"oop": "Object Oriented Programming"},
        embedder=embedder,
        threshold=0.84,
    )

    assert len(out) == 1
    assert out[0].canonical_id == "oop"
    assert out[0].method == "semantic"
    # tokens embedded first, then canonical labels.
    assert embedder.calls == [[token], ["Object Oriented Programming"]]


def test_without_embedder_a_semantic_only_match_is_not_suggested():
    out = suggest_aliases(
        [("programowanieobiektowe", 4)],
        {"oop": "Object Oriented Programming"},
        threshold=0.84,
    )
    assert out == []


def test_render_lists_suggestions_and_handles_empty():
    assert "No alias suggestions" in render_suggestions([])
    rendered = render_suggestions(
        [AliasSuggestion("js2", "javascript", 0.91, "lexical", 5)]
    )
    assert "js2 -> javascript" in rendered
    assert "lexical" in rendered
