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
