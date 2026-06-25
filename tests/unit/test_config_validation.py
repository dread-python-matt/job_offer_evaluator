import logging

import pytest

from app.config import DEV_API_KEY_ENCRYPTION_KEY, DEV_JWT_SECRET
from app.config_validation import InsecureConfigurationError, validate_runtime_config

_STRONG_SECRET = "x" * 32
_STRONG_ENCRYPTION_KEY = "Zr8mNq1pVwXyZaBcDeFgHiJkLmNoPqRsTuVwXyZ0123="


def _validate(**overrides):
    base = dict(
        app_env="production",
        jwt_secret=_STRONG_SECRET,
        api_key_encryption_key=_STRONG_ENCRYPTION_KEY,
        cookie_secure=True,
        cors_origins=["https://app.example.com"],
        workers=1,
    )
    base.update(overrides)
    return validate_runtime_config(**base)


# --- development: never blocks ---


def test_development_allows_dev_defaults():
    # The whole point of the dev defaults is zero-config local runs.
    _validate(app_env="development", jwt_secret=DEV_JWT_SECRET, cookie_secure=False)


# --- production: hard-fail on insecure config ---


def test_production_rejects_default_jwt_secret():
    with pytest.raises(InsecureConfigurationError, match="JWT_SECRET"):
        _validate(jwt_secret=DEV_JWT_SECRET)


def test_production_rejects_too_short_jwt_secret():
    with pytest.raises(InsecureConfigurationError, match="JWT_SECRET"):
        _validate(jwt_secret="short")


def test_production_rejects_default_api_key_encryption_key():
    with pytest.raises(InsecureConfigurationError, match="API_KEY_ENCRYPTION_KEY"):
        _validate(api_key_encryption_key=DEV_API_KEY_ENCRYPTION_KEY)


def test_production_rejects_insecure_cookies():
    with pytest.raises(InsecureConfigurationError, match="COOKIE_SECURE"):
        _validate(cookie_secure=False)


def test_production_rejects_wildcard_cors_origin():
    with pytest.raises(InsecureConfigurationError, match="CORS"):
        _validate(cors_origins=["*"])


def test_production_accepts_a_hardened_configuration():
    # Strong secret + secure cookies + explicit origins → boots without error.
    _validate()


def test_production_reports_all_problems_at_once():
    with pytest.raises(InsecureConfigurationError) as exc_info:
        _validate(jwt_secret=DEV_JWT_SECRET, cookie_secure=False, cors_origins=["*"])
    message = str(exc_info.value)
    assert "JWT_SECRET" in message
    assert "COOKIE_SECURE" in message
    assert "CORS" in message


# --- multi-worker warning (does not block) ---


def test_multiple_workers_warns_but_does_not_block(caplog):
    with caplog.at_level(logging.WARNING):
        _validate(workers=4)
    assert any("worker" in record.message.lower() for record in caplog.records)
