"""Tests for active application error types."""

import pytest

from src.core.exceptions import (
    AppError,
    ConfigurationError,
    DatabaseError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("error", "status", "kind"),
    [
        (ValidationError("bad input"), 400, "validation_error"),
        (NotFoundError("missing"), 404, "not_found_error"),
        (DatabaseError("db failed"), 500, "database_error"),
        (ConfigurationError("bad config"), 500, "configuration_error"),
        (
            ExternalServiceError("gateway failed", service="maestro"),
            503,
            "external_service_error",
        ),
    ],
)
def test_error_contract(error: AppError, status: int, kind: str):
    assert error.status_code == status
    assert error.error_type == kind
    assert error.to_dict()["message"] == error.message


def test_error_context_is_preserved():
    error = ValidationError("invalid symbol", symbol="???")

    assert error.to_dict()["symbol"] == "???"
