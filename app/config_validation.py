import logging

from app.config import (
    API_KEY_ENCRYPTION_KEY,
    APP_ENV,
    COOKIE_SECURE,
    CORS_ORIGINS,
    DEV_API_KEY_ENCRYPTION_KEY,
    DEV_JWT_SECRET,
    JWT_SECRET,
    MIN_JWT_SECRET_LENGTH,
    RATE_LIMITER_BACKEND,
    WORKERS,
)

_logger = logging.getLogger(__name__)

# Environments where the strict production checks are relaxed for zero-config local dev / CI.
# Everything else — including an unset APP_ENV (which defaults to "production") — is treated as
# production, so forgetting to set it fails closed rather than booting with the dev secrets.
_NON_PRODUCTION_ENVS = frozenset({"development", "dev", "test", "local"})


def is_non_production(app_env: str = APP_ENV) -> bool:
    """True when `app_env` is an explicit development/test value (the environments where the
    strict production checks are relaxed). Used to gate dev-only conveniences such as
    auto-seeding the demo login. An unset `APP_ENV` defaults to ``production``, so this returns
    False for it — dev conveniences stay off unless development is opted into explicitly."""
    return app_env in _NON_PRODUCTION_ENVS


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when running in a production-grade environment but the configuration is
    unsafe (e.g. the committed dev JWT/Fernet secret, non-secure cookies, wildcard CORS). The app
    refuses to boot rather than serve traffic with a known-insecure setup."""


def validate_runtime_config(
    *,
    app_env: str = APP_ENV,
    jwt_secret: str = JWT_SECRET,
    api_key_encryption_key: str = API_KEY_ENCRYPTION_KEY,
    cookie_secure: bool = COOKIE_SECURE,
    cors_origins: list[str] = CORS_ORIGINS,
    workers: int = WORKERS,
    rate_limiter_backend: str = RATE_LIMITER_BACKEND,
    logger: logging.Logger = _logger,
) -> None:
    """Fail fast on insecure production configuration; warn on risky-but-valid settings.

    Unless `app_env` is an explicit non-production value (`development`/`dev`/`test`/`local`),
    the configuration is treated as production and this raises `InsecureConfigurationError`,
    listing every problem found, when any of these hold:
      - `JWT_SECRET` is still the dev default or shorter than `MIN_JWT_SECRET_LENGTH`
        (a guessable secret lets anyone forge sessions);
      - `API_KEY_ENCRYPTION_KEY` is still the public dev default (anyone could decrypt stored keys);
      - cookies are not marked Secure (`COOKIE_SECURE` is false) — they could ride plaintext;
      - a wildcard (`*`) CORS origin is configured alongside credentialed requests.

    Because `APP_ENV` defaults to `production`, a deployment that forgets to set it is validated
    (fails closed) rather than silently booting with the committed dev secrets.

    Regardless of environment, it logs a warning when `WORKERS > 1` while still on the
    per-process in-memory rate limiter, since the throttle would then be multiplied per
    worker. Selecting the shared Redis backend (`RATE_LIMITER_BACKEND=redis`) silences it.
    """
    if workers > 1 and rate_limiter_backend != "redis":
        logger.warning(
            "WORKERS=%d but the in-memory rate limiter is per-process: login/registration "
            "throttling is multiplied per worker. Set RATE_LIMITER_BACKEND=redis (a shared "
            "store) for multi-worker deployments.",
            workers,
        )

    if app_env in _NON_PRODUCTION_ENVS:
        return

    problems: list[str] = []
    if jwt_secret == DEV_JWT_SECRET:
        problems.append("JWT_SECRET is the insecure dev default; set a strong unique secret.")
    elif len(jwt_secret) < MIN_JWT_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET is too short (< {MIN_JWT_SECRET_LENGTH} chars); use a long random secret."
        )
    if api_key_encryption_key == DEV_API_KEY_ENCRYPTION_KEY:
        problems.append(
            "API_KEY_ENCRYPTION_KEY is the public dev default; set a unique Fernet key so stored "
            "provider API keys aren't decryptable by anyone."
        )
    if not cookie_secure:
        problems.append("COOKIE_SECURE must be true in production so cookies are HTTPS-only.")
    if "*" in cors_origins:
        problems.append(
            "CORS origin '*' is not allowed with credentialed requests; list explicit origins."
        )

    if problems:
        raise InsecureConfigurationError(
            "Refusing to start in production with insecure configuration: " + " ".join(problems)
        )
