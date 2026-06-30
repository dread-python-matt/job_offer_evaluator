"""Password-strength policy.

A single source of truth for what makes a password acceptable, kept in the domain so it is
framework-independent and unit-testable on its own. The presentation layer (the auth request
schemas) enforces it at the API boundary; the frontend validators mirror it for fast feedback."""

MIN_PASSWORD_LENGTH = 8


def _is_special(char: str) -> bool:
    """A special character is anything that isn't a letter, a digit, or whitespace
    (so spaces in a passphrase don't, on their own, satisfy the requirement)."""
    return not char.isalnum() and not char.isspace()


def validate_password_strength(password: str) -> None:
    """Raise `ValueError` describing every unmet requirement, or return None when the
    password satisfies all of them: at least `MIN_PASSWORD_LENGTH` characters and at least
    one lowercase letter, one uppercase letter, one number, and one special character."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"be at least {MIN_PASSWORD_LENGTH} characters long")
    if not any(c.islower() for c in password):
        problems.append("contain a lowercase letter")
    if not any(c.isupper() for c in password):
        problems.append("contain an uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("contain a number")
    if not any(_is_special(c) for c in password):
        problems.append("contain a special character")
    if problems:
        raise ValueError("Password must " + ", ".join(problems) + ".")
