import pytest

from app.domain.password_policy import MIN_PASSWORD_LENGTH, validate_password_strength

_VALID = "Passw0rd!"  # 8+ chars, lower, upper, digit, special


def test_accepts_a_password_meeting_every_requirement():
    validate_password_strength(_VALID)  # does not raise


def test_min_length_is_eight():
    assert MIN_PASSWORD_LENGTH == 8


@pytest.mark.parametrize(
    "password, missing",
    [
        ("Pa1!", "at least 8 characters"),  # too short
        ("PASSW0RD!", "lowercase letter"),  # no lowercase
        ("passw0rd!", "uppercase letter"),  # no uppercase
        ("Password!", "number"),  # no digit
        ("Passw0rd1", "special character"),  # no special
    ],
)
def test_rejects_passwords_missing_a_requirement(password, missing):
    with pytest.raises(ValueError, match=missing):
        validate_password_strength(password)


def test_whitespace_alone_is_not_a_special_character():
    # A passphrase with spaces but no symbol still needs a real special character.
    with pytest.raises(ValueError, match="special character"):
        validate_password_strength("Correct horse 1")


def test_error_lists_all_unmet_requirements_at_once():
    with pytest.raises(ValueError) as exc:
        validate_password_strength("short")

    message = str(exc.value)
    assert "8 characters" in message
    assert "uppercase letter" in message
    assert "number" in message
    assert "special character" in message
