from email_validator import EmailNotValidError, validate_email

from app.application.ports import EmailValidator


class AllowAllEmailValidator(EmailValidator):
    """Treats every address as deliverable. Used when deliverability checking is disabled
    (e.g. tests, offline runs); syntax is still enforced upstream by the request schema."""

    def is_deliverable(self, email: str) -> bool:
        return True


class DnsEmailValidator(EmailValidator):
    """Confirms an address is deliverable by checking its domain (MX records) via
    email-validator. A `EmailNotValidError` means undeliverable; anything else (e.g. a
    transient resolver failure) propagates so it isn't silently treated as a bad address."""

    def is_deliverable(self, email: str) -> bool:
        try:
            validate_email(email, check_deliverability=True)
        except EmailNotValidError:
            return False
        return True
