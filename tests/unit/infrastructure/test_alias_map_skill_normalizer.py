import json

import pytest

from app.infrastructure.alias_map_skill_normalizer import (
    _DEFAULT_MAP_PATH,
    AliasMapSkillNormalizer,
)

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
    result = AliasMapSkillNormalizer(_SPEC, on_unknown=lambda raw, norm: seen.append((raw, norm)))
    out = result.normalize("Elixir")
    assert out.id == "elixir"
    assert out.source == "passthrough"
    assert seen == [("Elixir", "elixir")]


def test_exposes_canonical_labels_for_tooling():
    labels = _normalizer().canonical_labels
    assert labels["javascript"] == "JavaScript"  # explicit label
    assert labels["java"] == "java"  # no label declared -> defaults to the id


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


def test_default_map_resolves_expanded_aliases():
    n = AliasMapSkillNormalizer.from_default(on_unknown=None)
    assert n.normalize("Apache Kafka").id == "kafka"
    assert n.normalize("sklearn").id == "scikitlearn"
    assert n.normalize("obj-c").id == "objectivec"
    assert n.normalize("SQL Server").id == "mssql"
    assert n.normalize(".NET").id == "dotnet"  # bare ".net" (protected) resolves via alias
    assert n.normalize("PyTorch").id == "pytorch"  # new canonical resolves to itself
    assert n.normalize("uczenie głębokie").id == "deeplearning"  # PL phrase -> EN concept


def test_default_map_resolves_python_stack_and_llm_concepts():
    # Regression for the "unknown skill token" tail: core Python-stack libraries (Pydantic,
    # Alembic) and common CV concepts (Clean Code, LLM) that used to pass through unmapped.
    n = AliasMapSkillNormalizer.from_default(on_unknown=None)
    assert n.normalize("Pydantic").id == "pydantic"
    assert n.normalize("Alembic").id == "alembic"
    assert n.normalize("Clean Code").id == "cleancode"
    assert n.normalize("czysty kod").id == "cleancode"  # PL alias -> concept
    assert n.normalize("LLM").id == "llm"
    llm_integration = n.normalize("LLM integration")
    assert llm_integration.id == "llm"  # phrase alias -> concept
    assert llm_integration.source == "alias"
    assert n.normalize("Large Language Models").id == "llm"


def test_default_map_honors_its_never_merge_pairs():
    n = AliasMapSkillNormalizer.from_default(on_unknown=None)
    assert n.never_merge_pairs  # the seed declares some
    for a, b in n.never_merge_pairs:
        assert n.normalize(a).id != n.normalize(b).id


def test_default_map_resolves_researched_stack_aliases():
    n = AliasMapSkillNormalizer.from_default(on_unknown=None)
    cases = {
        "pg": "postgresql",
        "SCSS": "sass",
        "AngularJS": "angular",
        "ExpressJS": "express",
        "Django REST Framework": "django",
        "DRF": "django",
        "Ruby on Rails": "rails",
        "T-SQL": "mssql",
        "PL/SQL": "oracle",
        "Microsoft Azure": "azure",
        ".NET Framework": "dotnet",
        "ASP.NET Core": "dotnet",
        "bs4": "beautifulsoup",
        "Jinja2": "jinja",
        "Anaconda": "conda",
        "scikit": "scikitlearn",
        "OAuth2": "oauth",
        "Integration Tests": "integrationtesting",
        "Infrastructure as Code": "iac",
        "Generative AI": "genai",
        "inżynieria danych": "dataengineering",  # PL -> concept
        "programowanie funkcyjne": "functionalprogramming",  # PL -> concept
    }
    for raw, expected in cases.items():
        assert n.normalize(raw).id == expected, raw


def test_default_map_adds_python_ecosystem_canonicals():
    n = AliasMapSkillNormalizer.from_default(on_unknown=None)
    for raw, cid in [
        ("SQLAlchemy", "sqlalchemy"),
        ("Celery", "celery"),
        ("Poetry", "poetry"),
        ("Gunicorn", "gunicorn"),
        ("Uvicorn", "uvicorn"),
        ("Streamlit", "streamlit"),
        ("asyncio", "asyncio"),
        ("mypy", "mypy"),
        ("Ruff", "ruff"),
    ]:
        result = n.normalize(raw)
        assert result.id == cid
        assert result.source == "canonical"


def test_default_map_has_no_redundant_or_shadowing_aliases():
    # Each alias must earn its place: its normalized key must differ from the target and must not
    # collide with a canonical id (which it would silently shadow). Guards the growing map.
    spec = json.loads(_DEFAULT_MAP_PATH.read_text(encoding="utf-8"))
    n = AliasMapSkillNormalizer(spec, on_unknown=None)
    canonical_ids = set(spec["canonical"])
    for raw, target in spec["aliases"].items():
        assert target in canonical_ids, f"{raw!r} -> unknown canonical {target!r}"
        key = n._lookup_key(raw)
        assert key != target, f"redundant alias {raw!r} (already normalizes to {target!r})"
        assert key not in canonical_ids, f"alias {raw!r} shadows canonical {key!r}"
