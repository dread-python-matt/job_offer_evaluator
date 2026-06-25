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
    WORKERS,
)

_logger = logging.getLogger(__name__)


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when APP_ENV=production but the configuration is unsafe to run with
    (e.g. the dev JWT secret, non-secure cookies). The app refuses to boot rather than serve
    traffic with a known-insecure setup."""


def validate_runtime_config(
    *,
    app_env: str = APP_ENV,
    jwt_secret: str = JWT_SECRET,
    api_key_encryption_key: str = API_KEY_ENCRYPTION_KEY,
    cookie_secure: bool = COOKIE_SECURE,
    cors_origins: list[str] = CORS_ORIGINS,
    workers: int = WORKERS,
    logger: logging.Logger = _logger,
) -> None:
    """Fail fast on insecure production configuration; warn on risky-but-valid settings.

    In production (`APP_ENV=production`) this raises `InsecureConfigurationError`, listing
    every problem found, when any of these hold:
      - `JWT_SECRET` is still the dev default or shorter than `MIN_JWT_SECRET_LENGTH`
        (a guessable secret lets anyone forge sessions);
      - cookies are not marked Secure (`COOKIE_SECURE` is false) — they could ride plaintext;
      - a wildcard (`*`) CORS origin is configured alongside credentialed requests.

    Regardless of environment, it logs a warning when `WORKERS > 1`, because the bundled
    in-memory rate limiter is per-process and a multi-worker deploy needs a shared store.
    """
    if workers > 1:
        logger.warning(
            "WORKERS=%d but the in-memory rate limiter is per-process: login/registration "
            "throttling is multiplied per worker. Use a shared-store limiter (e.g. Redis) "
            "for multi-worker deployments.",
            workers,
        )

    if app_env != "production":
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
