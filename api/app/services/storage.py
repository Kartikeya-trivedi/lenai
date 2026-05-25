"""
boto3 object storage service — upload, download, presigned URLs, TTL cleanup.
"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from botocore.client import Config

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

class StorageService:
    """Manages media file storage in S3-compatible storage."""

    def __init__(self) -> None:
        endpoint = settings.MINIO_ENDPOINT
        # If it's a supabase URL and doesn't have http, we add it and append the path
        if endpoint.endswith(".supabase.co"):
            if not endpoint.startswith("http"):
                endpoint = f"https://{endpoint}"
            if "/storage/v1/s3" not in endpoint:
                endpoint = f"{endpoint}/storage/v1/s3"
        elif not endpoint.startswith("http"):
            protocol = "https" if settings.MINIO_USE_SSL else "http"
            endpoint = f"{protocol}://{endpoint}"

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.MINIO_ROOT_USER,
            aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
            region_name=settings.MINIO_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self.public_endpoint = settings.MINIO_PUBLIC_ENDPOINT
        self.bucket_inputs = settings.MINIO_BUCKET_INPUTS
        self.bucket_outputs = settings.MINIO_BUCKET_OUTPUTS
        
        try:
            self.ensure_buckets()
        except Exception as e:
            logger.warning("could_not_ensure_buckets", error=str(e))

    def ensure_buckets(self) -> None:
        """Create input/output buckets if they don't exist."""
        for bucket in [self.bucket_inputs, self.bucket_outputs]:
            try:
                self.client.head_bucket(Bucket=bucket)
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code')
                if error_code == '404':
                    self.client.create_bucket(Bucket=bucket)
                    logger.info("bucket_created", bucket=bucket)

    def upload_file(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file and return the object key."""
        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        logger.info("file_uploaded", bucket=bucket, key=key, size=len(data))
        return key

    def download_file(self, bucket: str, key: str) -> bytes:
        """Download a file and return its bytes."""
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
        except ClientError as e:
            logger.error("download_failed", bucket=bucket, key=key, error=str(e))
            raise

    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        ttl_hours: int = 24,
    ) -> str:
        """Generate a presigned download URL with TTL."""
        url = self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=ttl_hours * 3600
        )
        # Handle MinIO local Docker networking replacement, but ignore Supabase
        if settings.MINIO_ENDPOINT in url and settings.MINIO_PUBLIC_ENDPOINT and "supabase.co" not in settings.MINIO_ENDPOINT:
            url = url.replace(settings.MINIO_ENDPOINT, settings.MINIO_PUBLIC_ENDPOINT)
        return url

    def delete_file(self, bucket: str, key: str) -> None:
        """Delete a file from storage."""
        try:
            self.client.delete_object(Bucket=bucket, Key=key)
            logger.info("file_deleted", bucket=bucket, key=key)
        except ClientError as e:
            logger.error("delete_failed", bucket=bucket, key=key, error=str(e))

    def get_file_size(self, bucket: str, key: str) -> int:
        """Get file size in bytes."""
        try:
            response = self.client.head_object(Bucket=bucket, Key=key)
            return response['ContentLength']
        except ClientError:
            return 0

    def list_objects(self, bucket: str, prefix: str = "") -> list:
        """List objects in a bucket with optional prefix."""
        try:
            response = self.client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            if 'Contents' in response:
                class Obj:
                    def __init__(self, key):
                        self.object_name = key
                return [Obj(obj['Key']) for obj in response['Contents']]
            return []
        except ClientError:
            return []

    def check_health(self) -> tuple[bool, float]:
        """Check S3 connectivity."""
        import time
        start = time.monotonic()
        try:
            self.client.head_bucket(Bucket=self.bucket_inputs)
            latency = (time.monotonic() - start) * 1000
            return True, round(latency, 2)
        except Exception:
            latency = (time.monotonic() - start) * 1000
            return False, round(latency, 2)

_storage: Optional[StorageService] = None

def get_storage() -> StorageService:
    """Get or create the storage service singleton."""
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
