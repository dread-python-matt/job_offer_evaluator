from app.domain.api_keys import mask_key


def test_mask_key_keeps_a_recognisable_prefix_and_last_four():
    assert mask_key("sk-proj-ABCDEFGH1234") == "sk-…1234"


def test_mask_key_handles_a_gemini_style_key():
    assert mask_key("AIzaSyD-EXAMPLE-key-7890") == "AIz…7890"


def test_mask_key_fully_masks_a_key_too_short_to_hint_safely():
    # A key short enough that prefix+suffix would reveal all of it is fully hidden,
    # so the hint never exposes the whole secret.
    assert mask_key("abcdefg") == "…"
