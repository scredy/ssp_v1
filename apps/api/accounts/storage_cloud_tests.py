import errno
from unittest.mock import patch, PropertyMock

from botocore.exceptions import ClientError, EndpointConnectionError
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings
from storages.backends.s3 import S3Storage

from .storage_backends import (
    PrivateR2Storage,
    R2_LIMIT_BYTES,
    storage_errors,
)


class CloudStorageErrorTests(SimpleTestCase):

    def make_error(self, code):
        return ClientError(
            {"Error": {"Code": code, "Message": "Simulated error"}},
            "GetObject",
        )

    def test_missing_object_returns_file_not_found(self):
        for code in ("404", "NoSuchKey", "NotFound"):
            with self.subTest(code=code):
                with self.assertRaises(FileNotFoundError):
                    with storage_errors():
                        raise self.make_error(code)

    def test_permission_failure_is_handled(self):
        for code in ("403", "AccessDenied", "InvalidAccessKeyId"):
            with self.subTest(code=code):
                with self.assertRaises(PermissionError):
                    with storage_errors():
                        raise self.make_error(code)

    def test_cloud_service_failure_is_handled(self):
        with self.assertRaises(OSError):
            with storage_errors():
                raise self.make_error("ServiceUnavailable")

    def test_connection_failure_is_handled(self):
        with self.assertRaises(OSError):
            with storage_errors():
                raise EndpointConnectionError(
                    endpoint_url="https://example.invalid"
                )

    def test_sensitive_error_details_are_not_exposed(self):
        with self.assertRaises(OSError) as error:
            with storage_errors():
                raise ClientError(
                    {"Error": {
                        "Code": "InternalError",
                        "Message": "sensitive-test-information",
                    }},
                    "PutObject",
                )

        self.assertNotIn(
            "sensitive-test-information",
            str(error.exception),
        )


@override_settings(STORAGES={
    "default": {
        "BACKEND": "accounts.storage_backends.PrivateR2Storage",
        "OPTIONS": {"bucket_name": "test-photos"},
    },
    "private_documents": {
        "BACKEND": "accounts.storage_backends.PrivateR2Storage",
        "OPTIONS": {"bucket_name": "test-documents"},
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
})
class CloudStorageWriteTests(TestCase):

    def setUp(self):
        self.storage = PrivateR2Storage(
            bucket_name="test-photos",
            access_key="dummy",
            secret_key="dummy",
            endpoint_url="https://example.invalid",
            region_name="auto",
        )

    def test_upload_below_quota(self):
        with patch.object(
            PrivateR2Storage, "connection",
            new_callable=PropertyMock,
        ), patch(
            "accounts.storage_backends.r2_usage_bytes",
            return_value=1000,
        ), patch.object(
            S3Storage, "_save",
            return_value="test.webp",
        ) as save:

            result = self.storage._save(
                "test.webp",
                ContentFile(b"dummy data"),
            )

            self.assertEqual(result, "test.webp")
            save.assert_called_once()

    def test_upload_above_quota_never_reaches_cloud(self):
        with patch.object(
            PrivateR2Storage, "connection",
            new_callable=PropertyMock,
        ), patch(
            "accounts.storage_backends.r2_usage_bytes",
            return_value=R2_LIMIT_BYTES,
        ), patch.object(S3Storage, "_save") as save:

            with self.assertRaises(OSError) as error:
                self.storage._save(
                    "test.webp",
                    ContentFile(b"dummy data"),
                )

            self.assertEqual(error.exception.errno, errno.ENOSPC)
            save.assert_not_called()

    def test_usage_check_failure_prevents_upload(self):
        with patch.object(
            PrivateR2Storage, "connection",
            new_callable=PropertyMock,
        ), patch(
            "accounts.storage_backends.r2_usage_bytes",
            side_effect=EndpointConnectionError(
                endpoint_url="https://example.invalid"
            ),
        ), patch.object(S3Storage, "_save") as save:

            with self.assertRaises(OSError):
                self.storage._save(
                    "test.webp",
                    ContentFile(b"dummy data"),
                )

            save.assert_not_called()
