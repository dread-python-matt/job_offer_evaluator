from pathlib import Path

from app.domain.entities import Experience, Project, Skill, UserProfile
from app.infrastructure.markdown_profile_repository import MarkdownUserProfileRepository


def _profile() -> UserProfile:
    return UserProfile(
        summary="Backend developer focused on Python services.",
        skills=[Skill(name="Python", rating=5), Skill(name="FastAPI", rating=4)],
        projects=[
            Project(
                name="Evaluator",
                repository_link="https://github.com/user/evaluator",
                summary="Job offer matching app",
                date_from="2026-01",
                date_to="2026-06",
                tech_stack=["Python", "FastAPI", "Gradio"],
            )
        ],
        experience=[
            Experience(
                title="Backend Developer",
                company="Acme",
                description="Built internal APIs",
                date_from="2024-01",
                date_to="2025-12",
                tech_stack=["Python", "Postgres"],
            )
        ],
    )


def test_load_returns_none_when_file_does_not_exist(tmp_path: Path):
    repository = MarkdownUserProfileRepository(tmp_path / "user_profile.md")

    assert repository.load() is None


def test_save_writes_markdown_file(tmp_path: Path):
    file_path = tmp_path / "user_profile.md"
    repository = MarkdownUserProfileRepository(file_path)

    repository.save(_profile())

    assert file_path.exists()
    content = file_path.read_text(encoding="utf-8")
    assert "Backend developer focused on Python services." in content
    assert "Python: 5" in content
    assert "Evaluator" in content
    assert "Acme" in content


def test_save_then_load_round_trips_profile(tmp_path: Path):
    file_path = tmp_path / "user_profile.md"
    repository = MarkdownUserProfileRepository(file_path)
    profile = _profile()

    repository.save(profile)
    loaded = repository.load()

    assert loaded == profile


def test_load_empty_file_returns_profile_with_all_empty_fields(tmp_path: Path):
    file_path = tmp_path / "user_profile.md"
    file_path.write_text("", encoding="utf-8")
    repository = MarkdownUserProfileRepository(file_path)

    loaded = repository.load()

    assert loaded == UserProfile(summary="", skills=[], projects=[], experience=[])


def test_load_ignores_malformed_skill_lines_without_rating(tmp_path: Path):
    content = "## Skills\n- Python\n- FastAPI: 4\n"
    file_path = tmp_path / "user_profile.md"
    file_path.write_text(content, encoding="utf-8")
    repository = MarkdownUserProfileRepository(file_path)

    loaded = repository.load()

    assert len(loaded.skills) == 1
    assert loaded.skills[0] == Skill(name="FastAPI", rating=4)


def test_load_returns_empty_skills_when_skills_section_is_missing(tmp_path: Path):
    content = "## Summary\nA developer.\n## Experience\n"
    file_path = tmp_path / "user_profile.md"
    file_path.write_text(content, encoding="utf-8")
    repository = MarkdownUserProfileRepository(file_path)

    loaded = repository.load()

    assert loaded.skills == []
    assert loaded.summary == "A developer."


def test_load_returns_empty_projects_when_projects_section_is_missing(tmp_path: Path):
    content = "## Summary\nA developer.\n## Skills\n- Python: 5\n"
    file_path = tmp_path / "user_profile.md"
    file_path.write_text(content, encoding="utf-8")
    repository = MarkdownUserProfileRepository(file_path)

    loaded = repository.load()

    assert loaded.projects == []


def test_load_parses_project_with_no_tech_stack(tmp_path: Path):
    content = (
        "## Projects\n"
        "### My Project\n"
        "- Repository: https://github.com/user/repo\n"
        "- Period: 2026-01 - 2026-06\n"
        "\n"
        "A project with no tech stack listed.\n"
    )
    file_path = tmp_path / "user_profile.md"
    file_path.write_text(content, encoding="utf-8")
    repository = MarkdownUserProfileRepository(file_path)

    loaded = repository.load()

    assert len(loaded.projects) == 1
    assert loaded.projects[0].name == "My Project"
    assert loaded.projects[0].tech_stack == []


def test_load_parses_experience_with_missing_company(tmp_path: Path):
    content = (
        "## Experience\n"
        "### Backend Developer\n"
        "- Period: 2024-01 - 2025-12\n"
        "- Tech Stack: Python\n"
        "\n"
        "Some description.\n"
    )
    file_path = tmp_path / "user_profile.md"
    file_path.write_text(content, encoding="utf-8")
    repository = MarkdownUserProfileRepository(file_path)

    loaded = repository.load()

    assert len(loaded.experience) == 1
    assert loaded.experience[0].company == ""
    assert loaded.experience[0].title == "Backend Developer"


def test_load_handles_duplicate_section_headers_by_using_last_occurrence(tmp_path: Path):
    content = (
        "## Skills\n"
        "- Python: 5\n"
        "## Skills\n"
        "- Java: 3\n"
    )
    file_path = tmp_path / "user_profile.md"
    file_path.write_text(content, encoding="utf-8")
    repository = MarkdownUserProfileRepository(file_path)

    loaded = repository.load()

    assert len(loaded.skills) == 1
    assert loaded.skills[0] == Skill(name="Java", rating=3)
