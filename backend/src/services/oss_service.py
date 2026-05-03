"""
Alibaba Cloud OSS (Object Storage Service) client for file uploads.

This service handles secure file uploads to OSS with:
- Presigned URL generation for direct browser uploads
- File type validation (images only)
- Automatic content-type detection
- Secure temporary access URLs
- Support for both static credentials and STS (ECS instance role)
"""

import hashlib
import re

import oss2
import structlog
from oss2.credentials import EnvironmentVariableCredentialsProvider

from src.core.utils.date_utils import utcnow

logger = structlog.get_logger()

# Allowed MIME types for feedback image attachments
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes


class OSSService:
    """
    Service for uploading files to Alibaba Cloud OSS.

    Supports both direct uploads (backend) and presigned URLs (browser uploads).
    """

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str,
    ):
        """
        Initialize OSS client.

        Supports two authentication modes:
        1. Static credentials: Provide access_key_id and access_key_secret
        2. STS/ECS instance role: Leave credentials empty, uses EnvironmentVariableCredentialsProvider

        Args:
            access_key_id: Alibaba Cloud Access Key ID (empty for STS mode)
            access_key_secret: Alibaba Cloud Access Key Secret (empty for STS mode)
            endpoint: OSS endpoint (e.g., "oss-cn-shanghai.aliyuncs.com")
            bucket_name: OSS bucket name
        """
        self.endpoint = endpoint
        self.bucket_name = bucket_name

        # Ensure endpoint uses HTTPS for presigned URLs
        https_endpoint = (
            f"https://{endpoint}" if not endpoint.startswith("http") else endpoint
        )

        # Choose authentication method based on credentials availability
        if access_key_id and access_key_secret:
            # Static credentials mode (local development)
            auth = oss2.Auth(access_key_id, access_key_secret)
            auth_mode = "static"
        else:
            # STS/ECS instance role mode (production on ACK/ECS)
            # Uses OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET env vars
            # or falls back to ECS instance metadata
            credentials_provider = EnvironmentVariableCredentialsProvider()
            auth = oss2.ProviderAuth(credentials_provider)
            auth_mode = "sts"

        self.bucket = oss2.Bucket(auth, https_endpoint, bucket_name)

        logger.info(
            "OSS service initialized",
            bucket=bucket_name,
            endpoint=endpoint,
            auth_mode=auth_mode,
        )

    def generate_object_key(
        self,
        prefix: str,
        filename: str,
        user_id: str,
    ) -> str:
        """
        Generate unique OSS object key for a file.

        Format: {prefix}/{date}/{user_id}/{hash}_{filename}

        Args:
            prefix: Folder prefix (e.g., "feedback")
            filename: Original filename
            user_id: User ID for namespacing

        Returns:
            Unique object key
        """
        # Get current date for organization
        date_path = utcnow().strftime("%Y/%m/%d")

        # Generate hash from user_id + timestamp for uniqueness
        timestamp = utcnow().isoformat()
        hash_input = f"{user_id}_{timestamp}_{filename}"
        file_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:12]

        # Clean filename (sanitize: keep only alphanumeric, dash, underscore, dot)
        clean_filename = re.sub(r"[^\w\-.]", "_", filename)

        # Construct key: feedback/2025/10/30/{user_id}/{hash}_{filename}
        return f"{prefix}/{date_path}/{user_id}/{file_hash}_{clean_filename}"

    def generate_presigned_upload_url(
        self,
        object_key: str,
        content_type: str,
        expires_in_seconds: int = 300,
    ) -> dict[str, str]:
        """
        Generate presigned URL for direct browser upload to OSS.

        Args:
            object_key: OSS object key (path)
            content_type: MIME type of the file
            expires_in_seconds: URL expiration time (default: 5 minutes)

        Returns:
            Dict with 'url' and 'object_key'
        """
        # Generate presigned PUT URL
        url = self.bucket.sign_url(
            "PUT",
            object_key,
            expires_in_seconds,
            headers={
                "Content-Type": content_type,
            },
        )

        logger.info(
            "Generated presigned upload URL",
            object_key=object_key,
            content_type=content_type,
            expires_in=expires_in_seconds,
        )

        return {
            "url": url,
            "object_key": object_key,
        }

    def generate_presigned_download_url(
        self,
        object_key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """
        Generate presigned URL for downloading/viewing a file from OSS.

        Args:
            object_key: OSS object key (path)
            expires_in_seconds: URL expiration time (default: 1 hour)

        Returns:
            Presigned URL string
        """
        url = self.bucket.sign_url("GET", object_key, expires_in_seconds)

        logger.debug(
            "Generated presigned download URL",
            object_key=object_key,
            expires_in=expires_in_seconds,
        )

        return url

    def upload_file(
        self,
        object_key: str,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload file directly to OSS (backend upload).

        Args:
            object_key: OSS object key (path)
            file_data: File binary data
            content_type: MIME type

        Returns:
            Public URL of uploaded file
        """
        # Upload with content-type header
        result = self.bucket.put_object(
            object_key,
            file_data,
            headers={
                "Content-Type": content_type,
            },
        )

        # Construct public URL
        public_url = f"https://{self.bucket_name}.{self.endpoint}/{object_key}"

        logger.info(
            "File uploaded to OSS",
            object_key=object_key,
            content_type=content_type,
            status=result.status,
        )

        return public_url

    def delete_file(self, object_key: str) -> bool:
        """
        Delete file from OSS.

        Args:
            object_key: OSS object key (path)

        Returns:
            True if successful
        """
        try:
            result = self.bucket.delete_object(object_key)

            logger.info(
                "File deleted from OSS",
                object_key=object_key,
                status=result.status,
            )

            return result.status == 204

        except Exception as e:
            logger.error(
                "Failed to delete file from OSS",
                object_key=object_key,
                error=str(e),
            )
            return False

    def validate_image_type(self, content_type: str) -> bool:
        """
        Validate if content type is an allowed image format.

        Args:
            content_type: MIME type string

        Returns:
            True if allowed
        """
        return content_type in ALLOWED_IMAGE_TYPES

    def get_file_extension(self, content_type: str) -> str | None:
        """
        Get file extension from content type.

        Args:
            content_type: MIME type string

        Returns:
            File extension (e.g., ".png") or None
        """
        return ALLOWED_IMAGE_TYPES.get(content_type)


def get_oss_service(
    access_key_id: str = "",
    access_key_secret: str = "",
    endpoint: str = "oss-cn-shanghai.aliyuncs.com",
    bucket_name: str = "financial-agent-oss",
) -> OSSService:
    """
    Factory function to create OSS service instance.

    Args:
        access_key_id: Alibaba Cloud Access Key ID (empty for STS mode)
        access_key_secret: Alibaba Cloud Access Key Secret (empty for STS mode)
        endpoint: OSS endpoint
        bucket_name: OSS bucket name

    Returns:
        Configured OSSService instance
    """
    return OSSService(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        endpoint=endpoint,
        bucket_name=bucket_name,
    )
