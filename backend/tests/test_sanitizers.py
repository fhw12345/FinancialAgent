"""
Unit tests for shared sanitizers.

Tests text sanitization for API keys, passwords, and other sensitive data.
"""

from src.shared.sanitizers import (
    is_sensitive_field,
    sanitize_api_response,
    sanitize_exception_message,
    sanitize_text,
)

# ===== sanitize_text Tests =====


class TestSanitizeText:
    """Test sanitize_text function."""

    def test_sanitize_empty(self):
        """Test empty string returns empty."""
        assert sanitize_text("") == ""
        assert sanitize_text(None) is None

    def test_sanitize_no_sensitive(self):
        """Test text without sensitive keywords returns unchanged."""
        text = "This is a normal message with no secrets"
        result = sanitize_text(text)
        assert result == text

    def test_sanitize_apikey_equals(self):
        """Test apikey=VALUE pattern."""
        text = "Error: apikey=ABC123DEF456 is invalid"
        result = sanitize_text(text)
        assert "ABC123DEF456" not in result
        assert "apikey=****" in result

    def test_sanitize_apikey_colon(self):
        """Test apikey:VALUE pattern."""
        text = "Config: apikey: SECRETKEY123"
        result = sanitize_text(text)
        assert "SECRETKEY123" not in result
        assert "****" in result

    def test_sanitize_bearer_token(self):
        """Test Bearer token pattern."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
        result = sanitize_text(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "Bearer ****" in result

    def test_sanitize_password(self):
        """Test password pattern."""
        text = "password=mysecretpassword123"
        result = sanitize_text(text)
        assert "mysecretpassword123" not in result
        assert "password=****" in result

    def test_sanitize_custom_mask(self):
        """Test custom mask."""
        text = "apikey=SECRET123"
        result = sanitize_text(text, mask="[REDACTED]")
        assert "apikey=[REDACTED]" in result

    def test_sanitize_case_insensitive(self):
        """Test case insensitive matching."""
        text = "APIKEY=secret123 and ApiKey=OTHER456"
        result = sanitize_text(text)
        assert "secret123" not in result
        assert "OTHER456" not in result

    def test_sanitize_multiple_patterns(self):
        """Test multiple sensitive patterns in one string."""
        text = "apikey=KEY123 password=PASS456 Bearer TOKEN789"
        result = sanitize_text(text)
        assert "KEY123" not in result
        assert "PASS456" not in result
        assert "TOKEN789" not in result


# ===== sanitize_api_response Tests =====


class TestSanitizeApiResponse:
    """Test sanitize_api_response function."""

    def test_sanitize_empty_response(self):
        """Test empty/None response."""
        assert sanitize_api_response({}) == {}
        assert sanitize_api_response(None) is None

    def test_sanitize_error_message(self):
        """Test Error Message field."""
        response = {"Error Message": "Invalid apikey=SECRET123"}
        result = sanitize_api_response(response)
        assert "SECRET123" not in result["Error Message"]
        assert "****" in result["Error Message"]

    def test_sanitize_information_field(self):
        """Test Information field."""
        response = {"Information": "Rate limit with apikey=ABC123"}
        result = sanitize_api_response(response)
        assert "ABC123" not in result["Information"]

    def test_sanitize_note_field(self):
        """Test Note field."""
        response = {"Note": "Bearer eyJhbGciOiJIUzI1NiJ9.test"}
        result = sanitize_api_response(response)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result["Note"]

    def test_sanitize_multiple_fields(self):
        """Test multiple error fields."""
        response = {
            "error": "apikey=KEY1",
            "message": "password=PASS1",
            "detail": "token check failed",
        }
        result = sanitize_api_response(response)
        assert "KEY1" not in result["error"]
        assert "PASS1" not in result["message"]

    def test_sanitize_preserves_non_string(self):
        """Test non-string fields are preserved."""
        response = {"Error Message": "apikey=SECRET", "status_code": 401}
        result = sanitize_api_response(response)
        assert result["status_code"] == 401

    def test_sanitize_creates_copy(self):
        """Test original response is not modified."""
        response = {"Error Message": "apikey=SECRET"}
        result = sanitize_api_response(response)
        assert response["Error Message"] == "apikey=SECRET"
        assert result["Error Message"] != response["Error Message"]


# ===== sanitize_exception_message Tests =====


class TestSanitizeExceptionMessage:
    """Test sanitize_exception_message function."""

    def test_sanitize_value_error(self):
        """Test sanitizing ValueError message."""
        exc = ValueError("apikey=SECRET123 is invalid")
        result = sanitize_exception_message(exc)
        assert "SECRET123" not in result
        assert "****" in result

    def test_sanitize_generic_exception(self):
        """Test sanitizing generic Exception."""
        exc = Exception("Bearer token123 expired")
        result = sanitize_exception_message(exc)
        assert "token123" not in result

    def test_sanitize_no_sensitive_exception(self):
        """Test exception without sensitive data."""
        exc = ValueError("Simple error message")
        result = sanitize_exception_message(exc)
        assert result == "Simple error message"


# ===== is_sensitive_field Tests =====


class TestIsSensitiveField:
    """Test is_sensitive_field function."""

    def test_sensitive_api_key(self):
        """Test api_key is sensitive."""
        assert is_sensitive_field("api_key") is True
        assert is_sensitive_field("API_KEY") is True
        assert is_sensitive_field("apiKey") is True

    def test_sensitive_secret(self):
        """Test secret fields."""
        assert is_sensitive_field("secret") is True
        assert is_sensitive_field("client_secret") is True
        assert is_sensitive_field("SECRET_KEY") is True

    def test_sensitive_password(self):
        """Test password fields."""
        assert is_sensitive_field("password") is True
        assert is_sensitive_field("user_password") is True
        assert is_sensitive_field("PASSWORD") is True

    def test_sensitive_token(self):
        """Test token fields."""
        assert is_sensitive_field("token") is True
        assert is_sensitive_field("access_token") is True
        assert is_sensitive_field("refresh_token") is True

    def test_sensitive_credential(self):
        """Test credential fields."""
        assert is_sensitive_field("credential") is True
        assert is_sensitive_field("credentials") is True

    def test_sensitive_auth(self):
        """Test auth fields."""
        assert is_sensitive_field("auth") is True
        assert is_sensitive_field("authorization") is True
        assert is_sensitive_field("auth_key") is True

    def test_sensitive_bearer(self):
        """Test bearer fields."""
        assert is_sensitive_field("bearer") is True
        assert is_sensitive_field("bearer_token") is True

    def test_not_sensitive(self):
        """Test non-sensitive fields."""
        assert is_sensitive_field("username") is False
        assert is_sensitive_field("email") is False
        assert is_sensitive_field("name") is False
        assert is_sensitive_field("data") is False
        assert is_sensitive_field("user_id") is False
