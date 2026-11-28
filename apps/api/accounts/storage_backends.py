from contextlib import contextmanager
import errno
import logging

from django.db import connection, transaction

from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages
from storages.backends.s3 import S3Storage


@contextmanager
def storage_errors():
    try:
        yield
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))

        if code in {"404", "NoSuchKey", "NotFound"}:
            raise FileNotFoundError("Stored object not found.") from None

        if code in {"403", "AccessDenied", "InvalidAccessKeyId"}:
            raise PermissionError("Cloud storage access denied.") from None

        raise OSError("Cloud storage request failed.") from None

    except (BotoCoreError, S3UploadFailedError):
        raise OSError("Cloud storage connection failed.") from None


logger = logging.getLogger(__name__)

R2_WARNING_BYTES = 7_000_000_000
R2_LIMIT_BYTES = 8_000_000_000

# Shared PostgreSQL advisory lock for R2 uploads.
R2_UPLOAD_LOCK = 773001482


def r2_usage_bytes(client, bucket_names):
    total = 0
    paginator = client.get_paginator("list_objects_v2")

    for bucket in dict.fromkeys(bucket_names):
        for page in paginator.paginate(Bucket=bucket):
            total += sum(
                int(item["Size"])
                for item in page.get("Contents", [])
            )

    return total


def enforce_r2_quota(current_bytes, incoming_bytes):
    if incoming_bytes < 0:
        raise ValueError("Invalid upload size.")

    projected = current_bytes + incoming_bytes

    if projected > R2_LIMIT_BYTES:
        logger.warning("R2 upload blocked: storage quota reached.")
        raise OSError(
            errno.ENOSPC,
            "SSP cloud storage quota reached."
        )

    if projected >= R2_WARNING_BYTES:
        logger.warning(
            "R2 storage approaching limit: bytes=%s",
            projected,
        )

    return projected


class PrivateR2Storage(S3Storage):
    """Private object storage accessed through authorized Django endpoints."""

    def _open(self, name, mode="rb"):
        with storage_errors():
            file = super()._open(name, mode)

            if "r" in mode:
                try:
                    file.seek(0)
                except Exception:
                    file.close()
                    raise

            return file

    def _save(self, name, content):
        # Serialize storage writes across application workers.
        # The lock is automatically released when the transaction ends.
        if connection.vendor != "postgresql":
            raise RuntimeError("R2 quota protection requires PostgreSQL.")

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    [R2_UPLOAD_LOCK],
                )

            with storage_errors():
                buckets = (
                    settings.STORAGES["default"]["OPTIONS"]["bucket_name"],
                    settings.STORAGES["private_documents"]["OPTIONS"]["bucket_name"],
                )

                usage = r2_usage_bytes(
                    self.connection.meta.client,
                    buckets,
                )

                enforce_r2_quota(usage, content.size)

                return super()._save(name, content)

    def exists(self, name):
        with storage_errors():
            return super().exists(name)

    def delete(self, name):
        with storage_errors():
            return super().delete(name)

    def size(self, name):
        with storage_errors():
            return super().size(name)

    def url(self, name, *args, **kwargs):
        raise NotImplementedError(
            "Use the authorized SSP file access endpoint."
        )


class PrivateEvidenceStorage(FileSystemStorage):
    """Retains existing local storage behavior and migration compatibility."""

    @property
    def cloud_enabled(self):
        return getattr(settings, "SSP_STORAGE_BACKEND", "local") == "r2"

    @property
    def cloud_storage(self):
        return storages["private_documents"]

    def save(self, name, content, max_length=None):
        if self.cloud_enabled:
            return self.cloud_storage.save(name, content, max_length=max_length)
        return super().save(name, content, max_length=max_length)

    def open(self, name, mode="rb"):
        if self.cloud_enabled:
            return self.cloud_storage.open(name, mode)
        return super().open(name, mode)

    def exists(self, name):
        if self.cloud_enabled:
            return self.cloud_storage.exists(name)
        return super().exists(name)

    def delete(self, name):
        if self.cloud_enabled:
            return self.cloud_storage.delete(name)
        return super().delete(name)

    def size(self, name):
        if self.cloud_enabled:
            return self.cloud_storage.size(name)
        return super().size(name)

    def path(self, name):
        if self.cloud_enabled:
            raise NotImplementedError("R2 objects have no local filesystem path.")
        return super().path(name)

    def url(self, name):
        if self.cloud_enabled:
            return self.cloud_storage.url(name)
        return super().url(name)
