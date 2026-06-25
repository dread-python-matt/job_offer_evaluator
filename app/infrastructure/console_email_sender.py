import logging

from app.application.ports import EmailSender

_logger = logging.getLogger(__name__)


class ConsoleEmailSender(EmailSender):
    """Development fallback used when no SMTP server is configured: instead of delivering
    mail it logs the message (including any confirmation link) so the flow can be exercised
    locally without a mail server. Not for production use."""

    def send(self, to: str, subject: str, body: str) -> None:
        _logger.info(
            "[email] not sending over SMTP (no server configured)\n"
            "  to: %s\n  subject: %s\n  body:\n%s",
            to,
            subject,
            body,
        )
