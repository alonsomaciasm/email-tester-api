"""Unit tests for domain exception hierarchy and custom error handlers."""

from app.core.exceptions import (
    EmailFormatValidationError,
    InfrastructureUnavailableError,
    RateLimitExceededError,
)


def test_custom_domain_exceptions_contract() -> None:
    err1 = EmailFormatValidationError("Custom invalid email")
    assert err1.status_code == 422
    assert err1.code == "INVALID_EMAIL_FORMAT"
    assert err1.message == "Custom invalid email"

    err2 = RateLimitExceededError(retry_after=45)
    assert err2.status_code == 429
    assert err2.code == "RATE_LIMIT_EXCEEDED"
    assert err2.details["retry_after"] == 45

    err3 = InfrastructureUnavailableError("Redis")
    assert err3.status_code == 503
    assert err3.code == "INFRASTRUCTURE_UNAVAILABLE"
    assert "Redis" in err3.message
