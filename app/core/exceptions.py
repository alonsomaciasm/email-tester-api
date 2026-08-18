"""Enterprise Domain Exceptions Hierarchy.

Provides custom exception classes for domain failures, rate limits, infrastructure outages,
and input validation errors with standardized error codes and status mapping.
"""

from typing import Any


class AppBaseException(Exception):
    """Base class for all application domain exceptions."""

    def __init__(
        self,
        message: str = "An internal application error occurred.",
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class EmailFormatValidationError(AppBaseException):
    """Raised when input email format is invalid or fails IDNA domain validation."""

    def __init__(self, message: str = "Invalid email address format.") -> None:
        super().__init__(
            message=message,
            code="INVALID_EMAIL_FORMAT",
            status_code=422,
        )


class RateLimitExceededError(AppBaseException):
    """Raised when client exceeds sliding window rate limit."""

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after},
        )


class InfrastructureUnavailableError(AppBaseException):
    """Raised when critical infrastructure dependency (e.g. Redis) is unavailable."""

    def __init__(self, service_name: str) -> None:
        super().__init__(
            message=f"Infrastructure service '{service_name}' is currently unavailable.",
            code="INFRASTRUCTURE_UNAVAILABLE",
            status_code=503,
        )
