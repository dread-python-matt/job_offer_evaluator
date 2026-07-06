import logging

import pytest

from app.config import DEV_API_KEY_ENCRYPTION_KEY, DEV_JWT_SECRET
from app.config_validation import (
    InsecureConfigurationError,
    is_non_production,
    validate_runtime_config,
)

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
        rate_limiter_backend="memory",
    )
    base.update(overrides)
    return validate_runtime_config(**base)


# --- is_non_production: gates dev-only conveniences (e.g. the demo-login auto-seed) ---


def test_is_non_production_true_for_dev_envs():
    assert is_non_production("development")
    assert is_non_production("dev")
    assert is_non_production("test")
    assert is_non_production("local")


def test_is_non_production_false_for_production_and_unknown():
    # An unset APP_ENV defaults to "production", so anything unrecognized must be treated as
    # production — dev conveniences stay off unless development is opted into explicitly.
    assert not is_non_production("production")
    assert not is_non_production("staging")
    assert not is_non_production("")


# --- development: never blocks ---


def test_development_allows_dev_defaults():
    # The whole point of the dev defaults is zero-config local runs.
    _validate(app_env="development", jwt_secret=DEV_JWT_SECRET, cookie_secure=False)


def test_other_explicit_dev_aliases_also_allow_dev_defaults():
    for env in ("dev", "test", "local"):
        _validate(app_env=env, jwt_secret=DEV_JWT_SECRET, cookie_secure=False)


# --- fail closed: anything that isn't an explicit dev/test env is validated as production ---


def test_unset_or_unknown_env_is_treated_as_production():
    # Forgetting APP_ENV (it defaults to "production") or a typo like "prod"/"staging" must
    # NOT silently boot with the committed dev secret — it fails closed.
    for env in ("production", "prod", "staging", "", "PRODUCTION".lower()):
        with pytest.raises(InsecureConfigurationError, match="JWT_SECRET"):
            _validate(app_env=env, jwt_secret=DEV_JWT_SECRET, cookie_secure=False)


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


def test_multiple_workers_with_redis_backend_do_not_warn(caplog):
    # The Redis limiter is shared across workers, so WORKERS>1 is fine — no warning.
    with caplog.at_level(logging.WARNING):
        _validate(workers=4, rate_limiter_backend="redis")
    assert not any("worker" in record.message.lower() for record in caplog.records)
