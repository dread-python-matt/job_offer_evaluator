class AiScoringError(Exception):
    pass


class CostUnavailableError(Exception):
    """Raised when the daily cost cannot be determined (e.g. the usage API is
    unauthorized, lacks scopes, or is unreachable). Callers treat this as
    'budget unknown' and degrade gracefully rather than failing the request."""


class BudgetExceededError(Exception):
    def __init__(self, cost_usd: float, limit_usd: float) -> None:
        super().__init__(
            f"Daily OpenAI budget exceeded: ${cost_usd:.2f} spent of ${limit_usd:.2f} limit"
        )
        self.cost_usd = cost_usd
        self.limit_usd = limit_usd


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


class RateLimitExceededError(Exception):
    """Too many attempts within the limiter's window. Carries how many seconds the caller
    should wait before retrying, surfaced to clients as a Retry-After header."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many attempts; rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds
