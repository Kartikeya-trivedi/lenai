"""
MinIO object storage service — upload, download, presigned URLs, TTL cleanup.
"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class StorageService:
    """Manages media file storage in MinIO (S3-compatible)."""

    def __init__(self) -> None:
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=settings.MINIO_USE_SSL,
        )
        self.public_endpoint = settings.MINIO_PUBLIC_ENDPOINT
        self.bucket_inputs = settings.MINIO_BUCKET_INPUTS
        self.bucket_outputs = settings.MINIO_BUCKET_OUTPUTS
        
        # Ensure Supabase S3 buckets exist on startup
        try:
            self.ensure_buckets()
        except Exception as e:
            logger.warning("could_not_ensure_buckets", error=str(e))

    def ensure_buckets(self) -> None:
        """Create input/output buckets if they don't exist."""
        for bucket in [self.bucket_inputs, self.bucket_outputs]:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)
                logger.info("bucket_created", bucket=bucket)

    def upload_file(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file and return the object key."""
        stream = BytesIO(data)
        self.client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=stream,
            length=len(data),
            content_type=content_type,
        )
        logger.info("file_uploaded", bucket=bucket, key=key, size=len(data))
        return key

    def download_file(self, bucket: str, key: str) -> bytes:
        """Download a file and return its bytes."""
        try:
            response = self.client.get_object(bucket, key)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error("download_failed", bucket=bucket, key=key, error=str(e))
            raise

    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        ttl_hours: int = 24,
    ) -> str:
        """Generate a presigned download URL with TTL."""
        url = self.client.presigned_get_object(
            bucket_name=bucket,
            object_name=key,
            expires=timedelta(hours=ttl_hours),
        )
        # Replace internal endpoint with public-facing one
        url = url.replace(settings.MINIO_ENDPOINT, self.public_endpoint)
        return url

    def delete_file(self, bucket: str, key: str) -> None:
        """Delete a file from storage."""
        try:
            self.client.remove_object(bucket, key)
            logger.info("file_deleted", bucket=bucket, key=key)
        except S3Error as e:
            logger.error("delete_failed", bucket=bucket, key=key, error=str(e))

    def get_file_size(self, bucket: str, key: str) -> int:
        """Get file size in bytes."""
        try:
            stat = self.client.stat_object(bucket, key)
            return stat.size
        except S3Error:
            return 0

    def list_objects(self, bucket: str, prefix: str = "") -> list:
        """List objects in a bucket with optional prefix."""
        objects = self.client.list_objects(bucket, prefix=prefix)
        return [obj for obj in objects]

    def check_health(self) -> tuple[bool, float]:
        """Check MinIO connectivity."""
        import time

        start = time.monotonic()
        try:
            self.client.bucket_exists(self.bucket_inputs)
            latency = (time.monotonic() - start) * 1000
            return True, round(latency, 2)
        except Exception:
            latency = (time.monotonic() - start) * 1000
            return False, round(latency, 2)


# Module-level singleton
_storage: Optional[StorageService] = None


def get_storage() -> StorageService:
    """Get or create the storage service singleton."""
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
