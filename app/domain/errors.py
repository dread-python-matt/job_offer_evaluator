class AiScoringError(Exception):
    pass


class CostUnavailableError(Exception):
    """Raised when the daily cost cannot be determined (e.g. the usage API is
    unauthorized, lacks scopes, or is unreachable). Callers treat this as
    'budget unknown' and degrade gracefully rather than failing the request."""


class BudgetExceededError(Exception):
    def __init__(self, cost_usd: float, limit_usd: float) -> None:
        super().__init__(
            f"Budget exceeded: ${cost_usd:.2f} spent of ${limit_usd:.2f} limit"
        )
        self.cost_usd = cost_usd
        self.limit_usd = limit_usd


class DailyRequestLimitExceededError(Exception):
    """The user has reached their per-day request cap for a provider key (the free-tier
    requests-per-day, or their own override). Distinct from the USD `BudgetExceededError`
    so the message is request-framed rather than dollar-framed; both gate the AI match and
    map to HTTP 402."""

    def __init__(self, used: int, limit: int, model: str = "") -> None:
        target = f" for {model}" if model else ""
        super().__init__(
            f"Daily request limit reached{target}: {used} of {limit} requests today. "
            f"It resets at midnight US/Pacific; raise the limit or wait for the reset."
        )
        self.used = used
        self.limit = limit
        self.model = model


class EmailAlreadyRegisteredError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"Email already registered: {email}")
        self.email = email


class InvalidCredentialsError(Exception):
    """Wrong email or password. Deliberately does not say which, to avoid confirming
    whether an email is registered."""


class EmailNotVerifiedError(Exception):
    """Login was attempted against an account whose email has not been confirmed yet.
    The account exists and the password is correct, but the confirmation link emailed
    at registration has not been followed."""


class EmailAlreadyVerifiedError(Exception):
    """A confirmation link was followed for an account whose email is already verified.
    Confirmation links are single-use: once the account is verified the link no longer
    logs the user in, so a replayed/stale link is rejected rather than re-authenticating."""


class EmailNotDeliverableError(Exception):
    """The email address is syntactically valid but does not appear to be deliverable
    (e.g. its domain has no MX records). Surfaced at registration so obviously dead or
    mistyped domains fail fast before an account is created."""

    def __init__(self, email: str) -> None:
        super().__init__(f"Email address is not deliverable: {email}")
        self.email = email


class InvalidVerificationTokenError(Exception):
    """An email-confirmation token is missing, malformed, expired, has the wrong purpose,
    or no longer maps to a user. Deliberately opaque to avoid leaking which."""


class InvalidPasswordResetTokenError(Exception):
    """A password-reset token is missing, malformed, expired, has the wrong purpose, or no
    longer maps to a user. Deliberately opaque to avoid leaking which."""


class AuthenticationError(Exception):
    """A session token is missing, malformed, expired, or no longer matches the user
    (e.g. its token_version is stale)."""


class InvalidApiKeyError(Exception):
    """A provider API key the user supplied was rejected by the provider (e.g. a 401/403
    when listing models). Surfaced when adding a key so a wrong or revoked key fails fast
    before it is stored."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"The {provider} API key was rejected by the provider")
        self.provider = provider


class UnsupportedApiProviderError(Exception):
    """An API key was submitted for a provider the app does not support."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Unsupported API provider: {provider}")
        self.provider = provider


class ApiKeyAlreadyExistsError(Exception):
    """The user already has a key for this provider. Keys are one-per-provider; rotating
    means deleting the existing key first (changing only the budget is a separate action)."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"An API key for {provider} already exists")
        self.provider = provider


class ApiKeyNotFoundError(Exception):
    """No stored key for this user and provider (e.g. deleting or re-budgeting a key that
    isn't there)."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"No API key for {provider}")
        self.provider = provider


class InvalidAdminKeyError(Exception):
    """An OpenAI admin key the user supplied was rejected by the provider when reading the
    organization costs/usage API (e.g. a 401/403, or a key missing the `api.usage.read`
    scope). Surfaced when saving the admin key so a wrong or under-scoped key fails fast
    before it is stored.

    `reason` carries the provider's own error text when available, appended to the guidance
    so the user sees exactly why the key was refused (a bare, generic message is otherwise
    indistinguishable from a silent 'the key disappeared')."""

    def __init__(self, reason: str | None = None) -> None:
        message = (
            "The OpenAI admin key was rejected; it must be an organization admin key "
            "with the api.usage.read scope"
        )
        if reason:
            message = f"{message}. OpenAI said: {reason}"
        super().__init__(message)
        self.reason = reason


class MissingProviderApiKeyError(Exception):
    """An AI action needs the user's own API key for a provider, but they haven't added
    one. Surfaced (require-own-key) when a user tries to score/select a model for a
    provider they have no key for."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"No API key configured for {provider}; add one to use its models")
        self.provider = provider


class RateLimitExceededError(Exception):
    """Too many attempts within the limiter's window. Carries how many seconds the caller
    should wait before retrying, surfaced to clients as a Retry-After header."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many attempts; rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds
