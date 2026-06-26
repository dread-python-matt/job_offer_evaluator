from app.infrastructure.token_estimation import estimate_tokens


def test_estimates_about_four_characters_per_token():
    assert estimate_tokens("a" * 40) == 10


def test_empty_text_is_zero_tokens():
    assert estimate_tokens("") == 0


def test_rounds_up_a_partial_token():
    assert estimate_tokens("abcde") == 2  # 5 chars -> ceil(5/4)
