import pytest

from app.infrastructure.model_limits_registry import HardcodedModelLimitsRegistry


@pytest.fixture
def registry():
    return HardcodedModelLimitsRegistry()


def test_known_gemini_model_returns_limits(registry):
    limits = registry.get_limits("gemini-2.0-flash")

    assert limits is not None
    assert limits.rpm > 0
    assert limits.tpm > 0
    assert limits.rpd > 0


def test_unknown_model_returns_none(registry):
    limits = registry.get_limits("some-unknown-model-xyz")

    assert limits is None


def test_gemini_flash_free_tier_limits(registry):
    limits = registry.get_limits("gemini-2.0-flash")

    assert limits.rpm == 15
    assert limits.tpm == 1_000_000
    assert limits.rpd == 1500


def test_gemini_25_flash_limits(registry):
    limits = registry.get_limits("gemini-2.5-flash")

    assert limits is not None
    assert limits.rpm == 10
    assert limits.tpm == 250_000
    assert limits.rpd == 500


def test_gemini_15_flash_limits(registry):
    limits = registry.get_limits("gemini-1.5-flash")

    assert limits is not None
    assert limits.rpm == 15
    assert limits.tpm == 1_000_000
    assert limits.rpd == 1500
