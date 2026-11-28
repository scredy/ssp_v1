from unittest.mock import Mock
import errno

from django.test import SimpleTestCase

from .storage_backends import (
    R2_LIMIT_BYTES,
    R2_WARNING_BYTES,
    enforce_r2_quota,
    r2_usage_bytes,
)


class StorageQuotaTests(SimpleTestCase):
    def test_normal_upload_is_allowed(self):
        self.assertEqual(enforce_r2_quota(1000, 500), 1500)

    def test_warning_threshold(self):
        with self.assertLogs("accounts.storage_backends", level="WARNING"):
            self.assertEqual(
                enforce_r2_quota(R2_WARNING_BYTES - 100, 100),
                R2_WARNING_BYTES,
            )

    def test_exact_limit_is_allowed(self):
        self.assertEqual(
            enforce_r2_quota(R2_LIMIT_BYTES - 100, 100),
            R2_LIMIT_BYTES,
        )

    def test_upload_above_limit_is_rejected(self):
        with self.assertRaises(OSError) as error:
            enforce_r2_quota(R2_LIMIT_BYTES - 100, 101)

        self.assertEqual(error.exception.errno, errno.ENOSPC)

    def test_negative_upload_size_is_rejected(self):
        with self.assertRaises(ValueError):
            enforce_r2_quota(1000, -1)

    def test_usage_includes_both_buckets_and_all_pages(self):
        client = Mock()
        paginator = client.get_paginator.return_value

        paginator.paginate.side_effect = [
            [
                {"Contents": [{"Size": 100}, {"Size": 200}]},
                {"Contents": [{"Size": 300}]},
            ],
            [
                {"Contents": [{"Size": 400}]},
                {},
            ],
        ]

        self.assertEqual(
            r2_usage_bytes(client, ["photos", "documents"]),
            1000,
        )

        self.assertEqual(paginator.paginate.call_count, 2)

    def test_empty_bucket_has_zero_usage(self):
        client = Mock()
        client.get_paginator.return_value.paginate.return_value = [{}]

        self.assertEqual(r2_usage_bytes(client, ["photos"]), 0)

    def test_duplicate_bucket_names_are_counted_once(self):
        client = Mock()
        paginator = client.get_paginator.return_value

        paginator.paginate.return_value = [
            {"Contents": [{"Size": 500}]}
        ]

        self.assertEqual(
            r2_usage_bytes(client, ["photos", "photos"]),
            500,
        )

        paginator.paginate.assert_called_once_with(Bucket="photos")
