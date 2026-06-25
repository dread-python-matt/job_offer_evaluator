import logging

import pytest

from app.infrastructure.console_email_sender import ConsoleEmailSender
from app.infrastructure.smtp_email_sender import SmtpEmailSender


def test_console_sender_logs_recipient_subject_and_body(caplog):
    with caplog.at_level(logging.INFO):
        ConsoleEmailSender().send(
            to="dev@example.com",
            subject="Confirm your email",
            body="Open https://app.test/verify-email?token=abc to confirm.",
        )

    logged = caplog.text
    assert "dev@example.com" in logged
    assert "Confirm your email" in logged
    assert "https://app.test/verify-email?token=abc" in logged


class _FakeSmtp:
    def __init__(self) -> None:
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent: list[object] = []

    def __enter__(self) -> "_FakeSmtp":
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: object) -> None:
        self.sent.append(message)


def _sender(smtp: _FakeSmtp, **overrides):
    factory_calls = []

    def factory(host, port):
        factory_calls.append((host, port))
        return smtp

    kwargs = dict(
        host="smtp.test",
        port=587,
        username="mailer",
        password="secret",
        from_addr="noreply@app.test",
        use_tls=True,
    )
    kwargs.update(overrides)
    return SmtpEmailSender(**kwargs, smtp_factory=factory), factory_calls


def test_smtp_sender_sends_a_message_with_headers_and_body():
    smtp = _FakeSmtp()
    sender, factory_calls = _sender(smtp)

    sender.send(to="dev@example.com", subject="Confirm your email", body="the link")

    assert factory_calls == [("smtp.test", 587)]
    assert len(smtp.sent) == 1
    message = smtp.sent[0]
    assert message["To"] == "dev@example.com"
    assert message["From"] == "noreply@app.test"
    assert message["Subject"] == "Confirm your email"
    assert message.get_content().strip() == "the link"


def test_smtp_sender_starts_tls_and_logs_in_when_configured():
    smtp = _FakeSmtp()
    sender, _ = _sender(smtp)

    sender.send(to="dev@example.com", subject="s", body="b")

    assert smtp.started_tls is True
    assert smtp.login_args == ("mailer", "secret")


def test_smtp_sender_skips_login_when_no_credentials():
    smtp = _FakeSmtp()
    sender, _ = _sender(smtp, username="", password="")

    sender.send(to="dev@example.com", subject="s", body="b")

    assert smtp.login_args is None


def test_smtp_sender_skips_tls_when_disabled():
    smtp = _FakeSmtp()
    sender, _ = _sender(smtp, use_tls=False)

    sender.send(to="dev@example.com", subject="s", body="b")

    assert smtp.started_tls is False


def test_smtp_sender_rejects_newline_in_recipient():
    smtp = _FakeSmtp()
    sender, _ = _sender(smtp)

    # CR/LF in a header would let an attacker smuggle extra headers — reject it.
    with pytest.raises(ValueError):
        sender.send(to="dev@example.com\r\nBcc: victim@example.com", subject="s", body="b")

    assert smtp.sent == []


def test_smtp_sender_rejects_newline_in_subject():
    smtp = _FakeSmtp()
    sender, _ = _sender(smtp)

    with pytest.raises(ValueError):
        sender.send(to="dev@example.com", subject="hello\nX-Injected: 1", body="b")

    assert smtp.sent == []
