"""
Custom exception hierarchy for proper error categorization and HTTP status mapping.

This module provides a scalable exception system that maps internal errors to
appropriate HTTP status codes, improving debugging by clearly distinguishing:
- User errors (400-level): Client sent bad data
- Server errors (500-level): Our infrastructure/code failed
- External errors (502/503): Third-party services failed

Usage:
    from src.core.exceptions import DatabaseError, ExternalServiceError

    # Database errors → 500 Internal Server Error
    raise DatabaseError("Invalid database name: contains query parameters")

    # External API errors → 503 Service Unavailable
    raise ExternalServiceError("Agent Maestro timeout", service="maestro")
"""

from typing import Any


class AppError(Exception):
    """
    Base application error with HTTP status mapping.

    All custom exceptions inherit from this to enable consistent error handling.
    """

    # Default status code (subclasses override)
    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(self, message: str, **context: Any):
        """
        Initialize error with message and optional context.

        Args:
            message: Human-readable error description
            **context: Additional key-value pairs for logging (e.g., user_id, symbol)
        """
        super().__init__(message)
        self.message = message
        self.context = context

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON response and structured logging."""
        return {
            "error_type": self.error_type,
            "message": self.message,
            "status_code": self.status_code,
            **self.context,
        }


# ===== 400-level: Client Errors =====


class ValidationError(AppError):
    """User provided invalid input (e.g., malformed email, missing fields)."""

    status_code = 400
    error_type = "validation_error"


class NotFoundError(AppError):
    """Requested resource does not exist."""

    status_code = 404
    error_type = "not_found_error"


class RateLimitError(AppError):
    """User exceeded rate limit."""

    status_code = 429
    error_type = "rate_limit_error"


# ===== 500-level: Server Errors =====


class DatabaseError(AppError):
    """
    Database operation failed (connection, query, schema issues).

    Examples:
        - Connection timeout to MongoDB
        - Invalid collection name
        - Query execution error
        - Database name parsing issue

    Maps to 500 Internal Server Error (our infrastructure problem).
    """

    status_code = 500
    error_type = "database_error"


class CacheError(AppError):
    """Redis cache operation failed."""

    status_code = 500
    error_type = "cache_error"


class ConfigurationError(AppError):
    """
    Application misconfigured (e.g., missing env vars, invalid settings).

    Should be caught during startup, not during request handling.
    """

    status_code = 500
    error_type = "configuration_error"


# ===== 502/503: External Service Errors =====


class ExternalServiceError(AppError):
    """
    External service unavailable or returned error.

    Examples:
        - yfinance API rate limit
        - Agent Maestro timeout
        - Finnhub service error

    Maps to 503 Service Unavailable (third-party problem, retry may help).
    """

    status_code = 503
    error_type = "external_service_error"

    def __init__(self, message: str, service: str, **context: Any):
        """
        Initialize with service name for easier debugging.

        Args:
            message: Error description
            service: Service identifier (e.g., "tencent_ses", "yfinance")
            **context: Additional context (e.g., symbol, attempt_count)
        """
        super().__init__(message, service=service, **context)


# ===== Future Extensibility =====
#
# Add new exception types as needed:
#
# class StorageError(AppError):
#     """Cloud storage (OSS/S3) operation failed."""
#     status_code = 500
#     error_type = "storage_error"
#
# class ChartGenerationError(AppError):
#     """Chart rendering failed (matplotlib/plotting issue)."""
#     status_code = 500
#     error_type = "chart_generation_error"
#
# This scales well - each new error type:
# 1. Inherits from AppError
# 2. Sets appropriate status_code
# 3. Defines error_type for logging/monitoring
# 4. Optionally adds custom __init__ for domain-specific context
