"""
Unit tests for OSSService.

Tests Alibaba Cloud OSS file upload functionality.
"""

from unittest.mock import Mock, patch

import pytest

from src.services.oss_service import (
    ALLOWED_IMAGE_TYPES,
    MAX_FILE_SIZE,
    OSSService,
    get_oss_service,
)


# ===== Constants Tests =====


class TestOSSServiceConstants:
    """Test OSS service constants."""

    def test_allowed_image_types(self):
        """Test allowed image types."""
        assert "image/png" in ALLOWED_IMAGE_TYPES
        assert "image/jpeg" in ALLOWED_IMAGE_TYPES
        assert "image/gif" in ALLOWED_IMAGE_TYPES
        assert "image/webp" in ALLOWED_IMAGE_TYPES

    def test_max_file_size(self):
        """Test max file size is 10MB."""
        assert MAX_FILE_SIZE == 10 * 1024 * 1024


# ===== __init__ Tests =====


class TestOSSServiceInit:
    """Test OSSService initialization."""

    def test_init_with_static_credentials(self):
        """Test initialization with static credentials."""
        with patch("src.services.oss_service.oss2.Auth") as mock_auth:
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket:
                service = OSSService(
                    access_key_id="test_key",
                    access_key_secret="test_secret",
                    endpoint="oss-cn-shanghai.aliyuncs.com",
                    bucket_name="test-bucket",
                )

                assert service.endpoint == "oss-cn-shanghai.aliyuncs.com"
                assert service.bucket_name == "test-bucket"
                mock_auth.assert_called_once_with("test_key", "test_secret")

    def test_init_with_sts_mode(self):
        """Test initialization with STS mode (empty credentials)."""
        with patch("src.services.oss_service.EnvironmentVariableCredentialsProvider"):
            with patch("src.services.oss_service.oss2.ProviderAuth"):
                with patch("src.services.oss_service.oss2.Bucket"):
                    service = OSSService(
                        access_key_id="",
                        access_key_secret="",
                        endpoint="oss-cn-shanghai.aliyuncs.com",
                        bucket_name="test-bucket",
                    )

                    assert service.bucket_name == "test-bucket"

    def test_init_adds_https_to_endpoint(self):
        """Test initialization adds https to endpoint."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket:
                OSSService(
                    access_key_id="key",
                    access_key_secret="secret",
                    endpoint="oss-cn-shanghai.aliyuncs.com",
                    bucket_name="test-bucket",
                )

                # Should use https endpoint
                call_args = mock_bucket.call_args
                assert call_args[0][1].startswith("https://")


# ===== generate_object_key Tests =====


class TestGenerateObjectKey:
    """Test generate_object_key method."""

    def test_generates_key_with_prefix(self):
        """Test object key contains prefix."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                key = service.generate_object_key(
                    prefix="feedback",
                    filename="test.png",
                    user_id="user_123",
                )

                assert key.startswith("feedback/")

    def test_generates_key_with_user_id(self):
        """Test object key contains user_id."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                key = service.generate_object_key(
                    prefix="feedback",
                    filename="test.png",
                    user_id="user_123",
                )

                assert "user_123" in key

    def test_generates_unique_keys(self):
        """Test generates unique keys for same filename."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                # Mock utcnow to return different times
                with patch("src.services.oss_service.utcnow") as mock_time:
                    from datetime import datetime, timezone

                    mock_time.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
                    key1 = service.generate_object_key("prefix", "file.png", "user1")

                    mock_time.return_value = datetime(2025, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
                    key2 = service.generate_object_key("prefix", "file.png", "user1")

                assert key1 != key2

    def test_sanitizes_filename(self):
        """Test special characters in filename are sanitized."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                key = service.generate_object_key(
                    prefix="feedback",
                    filename="file with spaces!@#.png",
                    user_id="user_123",
                )

                # Should not contain spaces or special chars
                assert " " not in key
                assert "!" not in key
                assert "@" not in key
                assert "#" not in key


# ===== generate_presigned_upload_url Tests =====


class TestGeneratePresignedUploadUrl:
    """Test generate_presigned_upload_url method."""

    def test_returns_url_and_object_key(self):
        """Test returns dict with url and object_key."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket_class:
                mock_bucket = Mock()
                mock_bucket.sign_url.return_value = "https://signed-url.com"
                mock_bucket_class.return_value = mock_bucket

                service = OSSService("key", "secret", "endpoint", "bucket")

                result = service.generate_presigned_upload_url(
                    object_key="test/file.png",
                    content_type="image/png",
                )

                assert "url" in result
                assert "object_key" in result
                assert result["object_key"] == "test/file.png"

    def test_calls_sign_url_with_put(self):
        """Test calls sign_url with PUT method."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket_class:
                mock_bucket = Mock()
                mock_bucket.sign_url.return_value = "https://url.com"
                mock_bucket_class.return_value = mock_bucket

                service = OSSService("key", "secret", "endpoint", "bucket")

                service.generate_presigned_upload_url(
                    object_key="test/file.png",
                    content_type="image/png",
                    expires_in_seconds=600,
                )

                mock_bucket.sign_url.assert_called_once()
                call_args = mock_bucket.sign_url.call_args
                assert call_args[0][0] == "PUT"
                assert call_args[0][2] == 600


# ===== generate_presigned_download_url Tests =====


class TestGeneratePresignedDownloadUrl:
    """Test generate_presigned_download_url method."""

    def test_returns_signed_url(self):
        """Test returns signed download URL."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket_class:
                mock_bucket = Mock()
                mock_bucket.sign_url.return_value = "https://download-url.com"
                mock_bucket_class.return_value = mock_bucket

                service = OSSService("key", "secret", "endpoint", "bucket")

                url = service.generate_presigned_download_url("test/file.png")

                assert url == "https://download-url.com"
                mock_bucket.sign_url.assert_called()
                call_args = mock_bucket.sign_url.call_args
                assert call_args[0][0] == "GET"


# ===== upload_file Tests =====


class TestUploadFile:
    """Test upload_file method."""

    def test_uploads_file_returns_url(self):
        """Test uploads file and returns public URL."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket_class:
                mock_result = Mock()
                mock_result.status = 200

                mock_bucket = Mock()
                mock_bucket.put_object.return_value = mock_result
                mock_bucket_class.return_value = mock_bucket

                service = OSSService("key", "secret", "endpoint.com", "my-bucket")

                url = service.upload_file(
                    object_key="test/file.png",
                    file_data=b"file content",
                    content_type="image/png",
                )

                assert "my-bucket" in url
                assert "test/file.png" in url
                mock_bucket.put_object.assert_called_once()


# ===== delete_file Tests =====


class TestDeleteFile:
    """Test delete_file method."""

    def test_delete_returns_true_on_success(self):
        """Test delete returns True on status 204."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket_class:
                mock_result = Mock()
                mock_result.status = 204

                mock_bucket = Mock()
                mock_bucket.delete_object.return_value = mock_result
                mock_bucket_class.return_value = mock_bucket

                service = OSSService("key", "secret", "endpoint", "bucket")

                result = service.delete_file("test/file.png")

                assert result is True

    def test_delete_returns_false_on_error(self):
        """Test delete returns False on exception."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket") as mock_bucket_class:
                mock_bucket = Mock()
                mock_bucket.delete_object.side_effect = Exception("Delete failed")
                mock_bucket_class.return_value = mock_bucket

                service = OSSService("key", "secret", "endpoint", "bucket")

                result = service.delete_file("test/file.png")

                assert result is False


# ===== validate_image_type Tests =====


class TestValidateImageType:
    """Test validate_image_type method."""

    def test_valid_png(self):
        """Test PNG is valid."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                assert service.validate_image_type("image/png") is True

    def test_valid_jpeg(self):
        """Test JPEG is valid."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                assert service.validate_image_type("image/jpeg") is True

    def test_invalid_type(self):
        """Test invalid type returns False."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                assert service.validate_image_type("application/pdf") is False


# ===== get_file_extension Tests =====


class TestGetFileExtension:
    """Test get_file_extension method."""

    def test_get_png_extension(self):
        """Test gets .png extension."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                assert service.get_file_extension("image/png") == ".png"

    def test_get_jpeg_extension(self):
        """Test gets .jpg extension."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                assert service.get_file_extension("image/jpeg") == ".jpg"

    def test_unknown_type_returns_none(self):
        """Test unknown type returns None."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = OSSService("key", "secret", "endpoint", "bucket")

                assert service.get_file_extension("text/plain") is None


# ===== get_oss_service Tests =====


class TestGetOssService:
    """Test get_oss_service factory function."""

    def test_creates_service_with_defaults(self):
        """Test factory creates service with default values."""
        with patch("src.services.oss_service.oss2.ProviderAuth"):
            with patch("src.services.oss_service.EnvironmentVariableCredentialsProvider"):
                with patch("src.services.oss_service.oss2.Bucket"):
                    service = get_oss_service()

                    assert service.endpoint == "oss-cn-shanghai.aliyuncs.com"
                    assert service.bucket_name == "financial-agent-oss"

    def test_creates_service_with_custom_values(self):
        """Test factory creates service with custom values."""
        with patch("src.services.oss_service.oss2.Auth"):
            with patch("src.services.oss_service.oss2.Bucket"):
                service = get_oss_service(
                    access_key_id="custom_key",
                    access_key_secret="custom_secret",
                    endpoint="custom-endpoint.com",
                    bucket_name="custom-bucket",
                )

                assert service.endpoint == "custom-endpoint.com"
                assert service.bucket_name == "custom-bucket"
