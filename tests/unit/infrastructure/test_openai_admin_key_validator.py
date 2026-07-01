import logging
from types import SimpleNamespace
from unittest.mock import patch

import openai
import pytest

from app.domain.errors import InvalidAdminKeyError
from app.infrastructure.openai_admin_key_validator import OpenAIAdminKeyValidator


def _denied(status_code: int) -> openai.OpenAIError:
    return openai.PermissionDeniedError(
        message="Missing scopes: api.usage.read",
        response=SimpleNamespace(status_code=status_code, request=None, headers={}),
        body=None,
    )


def test_authenticates_with_admin_api_key_not_api_key():
    # Regression: admin/organization routes require `admin_api_key`. With `api_key` the SDK
    # raises a TypeError at request-build time (not an OpenAIError) -> 500 -> the key is never
    # stored and "disappears". Passing `admin_api_key` is what makes validation work at all.
    with patch("app.infrastructure.openai_admin_key_validator.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.return_value = (
            SimpleNamespace(data=[])
        )
        OpenAIAdminKeyValidator(timeout=5).validate("sk-admin-key")

    assert mock_cls.call_args.kwargs.get("admin_api_key") == "sk-admin-key"
    assert "api_key" not in mock_cls.call_args.kwargs


def test_passes_when_the_costs_call_succeeds():
    with patch("app.infrastructure.openai_admin_key_validator.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.return_value = (
            SimpleNamespace(data=[])
        )
        OpenAIAdminKeyValidator().validate("sk-admin-key")  # does not raise


@pytest.mark.parametrize("status", [400, 401, 403])
def test_rejects_bad_or_underscoped_key(status: int):
    with patch("app.infrastructure.openai_admin_key_validator.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.side_effect = _denied(
            status
        )

        with pytest.raises(InvalidAdminKeyError):
            OpenAIAdminKeyValidator().validate("sk-bad")


def test_rejection_surfaces_the_providers_actual_reason():
    # The generic "must have api.usage.read" guess isn't enough when a real sk-admin- key is
    # refused for a specific reason (a missing scope, a non-owner key, ...). Surface OpenAI's
    # own message verbatim so the user can see exactly why their key was rejected and fix it,
    # instead of a silent "the key disappeared".
    with patch("app.infrastructure.openai_admin_key_validator.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.side_effect = _denied(403)

        with pytest.raises(InvalidAdminKeyError) as exc_info:
            OpenAIAdminKeyValidator().validate("sk-admin-underscoped")

    assert "Missing scopes: api.usage.read" in str(exc_info.value)


def test_logs_a_warning_with_the_reason_when_the_key_is_rejected(caplog):
    # The reason must also reach the server logs (the readouts swallow it), so an operator can
    # diagnose a rejected key without a debugger.
    with patch("app.infrastructure.openai_admin_key_validator.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.side_effect = _denied(401)

        with caplog.at_level(logging.WARNING):
            with pytest.raises(InvalidAdminKeyError):
                OpenAIAdminKeyValidator().validate("sk-admin-x")

    assert any("Missing scopes: api.usage.read" in r.getMessage() for r in caplog.records)


def test_reraises_transient_errors_rather_than_misreporting_a_bad_key():
    # A 429/5xx is an outage, not a bad key — it must bubble (not become InvalidAdminKeyError),
    # so a transient failure isn't permanently misattributed to the user's key.
    with patch("app.infrastructure.openai_admin_key_validator.OpenAI") as mock_cls:
        mock_cls.return_value.admin.organization.usage.costs.side_effect = _denied(503)

        with pytest.raises(openai.OpenAIError):
            OpenAIAdminKeyValidator().validate("sk-admin-key")
