import pytest

from app.infrastructure.alias_map_skill_normalizer import AliasMapSkillNormalizer

_SPEC = {
    "canonical": {
        "javascript": {"label": "JavaScript"},
        "java": {},
        "kubernetes": {},
        "nodejs": {},
        "csharp": {},
        "cplusplus": {},
        "c": {},
        "dotnet": {},
        "database": {},
        "easy": {},
    },
    "aliases": {
        "js": "javascript",
        "k8s": "kubernetes",
        "node.js": "nodejs",
        "c#": "csharp",
        "c++": "cplusplus",
        "baza danych": "database",
        "latwy": "easy",  # exercises the ł→l fold (input "łatwy")
        ".net": "dotnet",  # protected: the leading dot must survive separator-collapsing
    },
    "protected": [".net"],
    "never_merge": [["java", "javascript"], ["c", "csharp"], ["c", "cplusplus"]],
}


def _normalizer(on_unknown=None) -> AliasMapSkillNormalizer:
    return AliasMapSkillNormalizer(_SPEC, on_unknown=on_unknown)


def test_alias_resolves_to_canonical():
    result = _normalizer().normalize("JS")
    assert result.id == "javascript"
    assert result.source == "alias"


def test_token_already_canonical_resolves_to_itself():
    result = _normalizer().normalize("JavaScript")
    assert result.id == "javascript"
    assert result.source == "canonical"


def test_matching_is_case_insensitive():
    assert _normalizer().normalize("K8S").id == "kubernetes"


def test_generic_accents_are_folded():
    assert _normalizer().normalize("Jáva").id == "java"


def test_polish_l_with_stroke_is_folded():
    # "ł" has no NFKD decomposition, so it relies on the explicit fold table.
    assert _normalizer().normalize("łatwy").id == "easy"


def test_pl_en_phrase_alias_resolves():
    assert _normalizer().normalize("Baza Danych").id == "database"


@pytest.mark.parametrize("raw", ["Node.js", "node js", "node-js", "NODE.JS"])
def test_separators_are_collapsed(raw):
    assert _normalizer().normalize(raw).id == "nodejs"


def test_protected_token_keeps_its_leading_dot():
    assert _normalizer().normalize(".NET").id == "dotnet"


def test_punctuation_significant_names_survive():
    n = _normalizer()
    assert n.normalize("C++").id == "cplusplus"
    assert n.normalize("C#").id == "csharp"


def test_unknown_token_passes_through_and_is_recorded():
    seen: list[tuple[str, str]] = []
    result = AliasMapSkillNormalizer(
        _SPEC, on_unknown=lambda raw, norm: seen.append((raw, norm))
    )
    out = result.normalize("Elixir")
    assert out.id == "elixir"
    assert out.source == "passthrough"
    assert seen == [("Elixir", "elixir")]


# --- known non-merges (regression guard against over-merging) ---


def test_java_is_not_javascript():
    n = _normalizer()
    assert n.normalize("Java").id != n.normalize("JavaScript").id


def test_c_family_stays_distinct():
    n = _normalizer()
    assert {n.normalize(x).id for x in ("C", "C#", "C++")} == {
        "c",
        "csharp",
        "cplusplus",
    }


# --- the shipped default map ---


def test_default_map_resolves_common_aliases():
    n = AliasMapSkillNormalizer.from_default(on_unknown=None)
    assert n.normalize("JS").id == "javascript"
    assert n.normalize("postgres").id == "postgresql"
    assert n.normalize("golang").id == "go"
    assert n.normalize("k8s").id == "kubernetes"


def test_default_map_honors_its_never_merge_pairs():
    n = AliasMapSkillNormalizer.from_default(on_unknown=None)
    assert n.never_merge_pairs  # the seed declares some
    for a, b in n.never_merge_pairs:
        assert n.normalize(a).id != n.normalize(b).id
