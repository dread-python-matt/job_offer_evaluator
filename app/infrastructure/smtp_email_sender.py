import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from app.application.ports import EmailSender

# A factory returning an SMTP client usable as a context manager (smtplib.SMTP is one).
# Injectable so the sender can be tested without a real server.
SmtpFactory = Callable[[str, int], smtplib.SMTP]


class SmtpEmailSender(EmailSender):
    """Sends plain-text email over SMTP using the standard library. STARTTLS and login
    are applied only when enabled/credentialled, so it works against both authenticated
    relays and open local dev servers."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
        use_tls: bool = True,
        smtp_factory: SmtpFactory = smtplib.SMTP,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_addr = from_addr
        self._use_tls = use_tls
        self._smtp_factory = smtp_factory

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from_addr
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with self._smtp_factory(self._host, self._port) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)
