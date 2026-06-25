import email_validator
import pytest

from app.infrastructure.email_validators import AllowAllEmailValidator, DnsEmailValidator


def test_allow_all_accepts_any_address():
    assert AllowAllEmailValidator().is_deliverable("anyone@whatever.invalid") is True


def test_dns_validator_returns_true_when_the_address_is_deliverable(monkeypatch):
    calls = {}

    def fake_validate_email(email, **kwargs):
        calls["email"] = email
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "app.infrastructure.email_validators.validate_email", fake_validate_email
    )

    assert DnsEmailValidator().is_deliverable("dev@example.com") is True
    assert calls["email"] == "dev@example.com"
    assert calls["kwargs"].get("check_deliverability") is True


def test_dns_validator_returns_false_when_the_domain_is_not_deliverable(monkeypatch):
    def fake_validate_email(email, **kwargs):
        raise email_validator.EmailNotValidError("no MX records")

    monkeypatch.setattr(
        "app.infrastructure.email_validators.validate_email", fake_validate_email
    )

    assert DnsEmailValidator().is_deliverable("dev@nonexistent.invalid") is False


def test_dns_validator_propagates_unexpected_errors(monkeypatch):
    def fake_validate_email(email, **kwargs):
        raise RuntimeError("DNS resolver crashed")

    monkeypatch.setattr(
        "app.infrastructure.email_validators.validate_email", fake_validate_email
    )

    with pytest.raises(RuntimeError):
        DnsEmailValidator().is_deliverable("dev@example.com")
