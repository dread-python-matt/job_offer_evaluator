from app.observability.request_context import (
    bind_request_id,
    get_request_id,
    reset_request_id,
)


def test_unset_outside_a_request_is_none():
    assert get_request_id() is None


def test_bind_then_get_returns_the_id():
    token = bind_request_id("abc123")
    try:
        assert get_request_id() == "abc123"
    finally:
        reset_request_id(token)


def test_reset_restores_the_previous_value():
    token = bind_request_id("abc123")
    reset_request_id(token)

    assert get_request_id() is None


def test_reset_unwinds_nested_binds():
    outer = bind_request_id("outer")
    inner = bind_request_id("inner")
    assert get_request_id() == "inner"

    reset_request_id(inner)
    assert get_request_id() == "outer"

    reset_request_id(outer)
    assert get_request_id() is None
