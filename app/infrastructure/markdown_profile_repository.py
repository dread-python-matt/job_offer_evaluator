import re
from pathlib import Path

from app.application.ports import UserProfileRepository
from app.domain.entities import Experience, Project, Skill, UserProfile

_SKILL_LINE = re.compile(r"^-\s*(?P<name>.+?):\s*(?P<rating>\d)\s*$")
_PERIOD_LINE = re.compile(r"^-\s*Period:\s*(?P<from>.*?)\s+-\s+(?P<to>.*?)\s*$")
_TECH_STACK_LINE = re.compile(r"^-\s*Tech Stack:\s*(?P<stack>.*)$")
_REPOSITORY_LINE = re.compile(r"^-\s*Repository:\s*(?P<link>.*)$")
_COMPANY_LINE = re.compile(r"^-\s*Company:\s*(?P<company>.*)$")


def _format_tech_stack(tech_stack: list[str]) -> str:
    return ", ".join(tech_stack)


def _parse_tech_stack(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class MarkdownUserProfileRepository(UserProfileRepository):
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def save(self, profile: UserProfile) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(self._render(profile), encoding="utf-8")

    def load(self) -> UserProfile | None:
        if not self._file_path.exists():
            return None
        return self._parse(self._file_path.read_text(encoding="utf-8"))

    def _render(self, profile: UserProfile) -> str:
        lines = ["# User Profile", "", "## Summary", profile.summary, "", "## Skills"]
        for skill in profile.skills:
            lines.append(f"- {skill.name}: {skill.rating}")

        lines += ["", "## Projects"]
        for project in profile.projects:
            lines += [
                f"### {project.name}",
                f"- Repository: {project.repository_link}",
                f"- Period: {project.date_from} - {project.date_to}",
                f"- Tech Stack: {_format_tech_stack(project.tech_stack)}",
                "",
                project.summary,
                "",
            ]

        lines += ["## Experience"]
        for experience in profile.experience:
            lines += [
                f"### {experience.title}",
                f"- Company: {experience.company}",
                f"- Period: {experience.date_from} - {experience.date_to}",
                f"- Tech Stack: {_format_tech_stack(experience.tech_stack)}",
                "",
                experience.description,
                "",
            ]

        return "\n".join(lines).rstrip() + "\n"

    def _parse(self, content: str) -> UserProfile:
        lines = content.splitlines()
        sections = self._split_sections(lines)

        summary = "\n".join(sections.get("Summary", [])).strip()
        skills = self._parse_skills(sections.get("Skills", []))
        projects = self._parse_projects(sections.get("Projects", []))
        experience = self._parse_experience(sections.get("Experience", []))

        return UserProfile(summary=summary, skills=skills, projects=projects, experience=experience)

    @staticmethod
    def _split_sections(lines: list[str]) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for line in lines:
            if line.startswith("## "):
                current = line[3:].strip()
                sections[current] = []
            elif current is not None and not line.startswith("# "):
                sections[current].append(line)
        return sections

    @staticmethod
    def _parse_skills(lines: list[str]) -> list[Skill]:
        skills = []
        for line in lines:
            match = _SKILL_LINE.match(line)
            if match:
                skills.append(Skill(name=match["name"].strip(), rating=int(match["rating"])))
        return skills

    @staticmethod
    def _split_entries(lines: list[str]) -> list[list[str]]:
        entries: list[list[str]] = []
        for line in lines:
            if line.startswith("### "):
                entries.append([line])
            elif entries:
                entries[-1].append(line)
        return entries

    @classmethod
    def _parse_projects(cls, lines: list[str]) -> list[Project]:
        projects = []
        for entry in cls._split_entries(lines):
            name = entry[0][4:].strip()
            link = ""
            date_from = date_to = ""
            tech_stack: list[str] = []
            summary_lines: list[str] = []
            for line in entry[1:]:
                if match := _REPOSITORY_LINE.match(line):
                    link = match["link"].strip()
                elif match := _PERIOD_LINE.match(line):
                    date_from, date_to = match["from"], match["to"]
                elif match := _TECH_STACK_LINE.match(line):
                    tech_stack = _parse_tech_stack(match["stack"])
                elif line.strip():
                    summary_lines.append(line)
            projects.append(
                Project(
                    name=name,
                    repository_link=link,
                    summary="\n".join(summary_lines).strip(),
                    date_from=date_from,
                    date_to=date_to,
                    tech_stack=tech_stack,
                )
            )
        return projects

    @classmethod
    def _parse_experience(cls, lines: list[str]) -> list[Experience]:
        experience = []
        for entry in cls._split_entries(lines):
            title = entry[0][4:].strip()
            company = ""
            date_from = date_to = ""
            tech_stack: list[str] = []
            description_lines: list[str] = []
            for line in entry[1:]:
                if match := _COMPANY_LINE.match(line):
                    company = match["company"].strip()
                elif match := _PERIOD_LINE.match(line):
                    date_from, date_to = match["from"], match["to"]
                elif match := _TECH_STACK_LINE.match(line):
                    tech_stack = _parse_tech_stack(match["stack"])
                elif line.strip():
                    description_lines.append(line)
            experience.append(
                Experience(
                    title=title,
                    company=company,
                    description="\n".join(description_lines).strip(),
                    date_from=date_from,
                    date_to=date_to,
                    tech_stack=tech_stack,
                )
            )
        return experience
