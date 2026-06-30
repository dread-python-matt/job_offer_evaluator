from app.infrastructure.postgres_offer_repository import _like_escape


def test_escapes_percent_and_underscore_wildcards():
    # `c%` should match the literal characters, not "anything starting with c".
    assert _like_escape("c%") == "c\\%"
    assert _like_escape("a_b") == "a\\_b"


def test_escapes_the_escape_character_itself_first():
    # A literal backslash must be doubled so it isn't read as escaping the next char.
    assert _like_escape("a\\b") == "a\\\\b"


def test_leaves_ordinary_text_untouched():
    assert _like_escape("python") == "python"
