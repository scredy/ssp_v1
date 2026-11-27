import errno
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from .models import User, Vehicle, VehiclePhoto


class InventoryPhotoUploadTests(APITestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory(prefix="ssp-photo-tests-")
        self.addCleanup(self.media_dir.cleanup)
        override = override_settings(MEDIA_ROOT=Path(self.media_dir.name) / "media")
        override.enable()
        self.addCleanup(override.disable)
        self.staff = User.objects.create_user(
            username="photo-staff", password="Strong-password-914!", email="photo-staff@example.test",
            role=User.Role.STAFF,
        )
        self.client.force_authenticate(self.staff)

    def vehicle_payload(self, identifier="PHOTO-CHASSIS-001", **overrides):
        return {
            "make": "Toyota", "model": "Prius", "variant": "", "manufacture_year": 2022,
            "mileage_km": 12000, "fuel_type": "hybrid", "transmission": "automatic", "color": "Silver",
            "condition": "used", "internal_identifier": identifier, "asking_price_lkr": "12500000.00",
            "description": "Photo upload test", "visibility": "draft", "status": "available", **overrides,
        }

    @staticmethod
    def image_upload(name="vehicle.png", color=(220, 20, 30)):
        stream = io.BytesIO()
        Image.new("RGB", (12, 8), color).save(stream, format="PNG")
        return SimpleUploadedFile(name, stream.getvalue(), content_type="image/png")

    def create_vehicle(self, identifier="PHOTO-CHASSIS-001", **overrides):
        response = self.client.post("/api/staff/inventory/", self.vehicle_payload(identifier, **overrides), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def upload(self, reference, *files):
        return self.client.post(f"/api/staff/inventory/{reference}/photos/", {"photos": list(files)}, format="multipart")

    def test_vehicle_creation_without_photos_and_duplicate_chassis_rejection(self):
        created = self.create_vehicle()
        self.assertEqual(created["photos"], [])
        self.assertEqual(self.client.post("/api/staff/inventory/", self.vehicle_payload(), format="json").status_code, 400)
        self.assertEqual(Vehicle.objects.filter(internal_identifier="PHOTO-CHASSIS-001").count(), 1)

    def test_vehicle_creation_then_multiple_photo_upload_and_retry_are_idempotent(self):
        vehicle = self.create_vehicle()
        first = self.image_upload("front.png", (1, 2, 3))
        second = self.image_upload("rear.png", (4, 5, 6))
        response = self.upload(vehicle["reference"], first, second)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["photos"]), 2)
        self.assertEqual(VehiclePhoto.objects.filter(vehicle__reference=vehicle["reference"]).count(), 2)

        retry = self.upload(vehicle["reference"], self.image_upload("front-again.png", (1, 2, 3)))
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(VehiclePhoto.objects.filter(vehicle__reference=vehicle["reference"]).count(), 2)

    def test_storage_permission_error_is_logged_safely_and_vehicle_is_preserved(self):
        vehicle = self.create_vehicle("PHOTO-STORAGE-DENIED")
        with patch.object(FileSystemStorage, "_save", side_effect=PermissionError(errno.EACCES, "private path")):
            with self.assertLogs("accounts.views", level="ERROR") as logs:
                response = self.upload(vehicle["reference"], self.image_upload())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Vehicle.objects.filter(reference=vehicle["reference"]).count(), 1)
        self.assertEqual(VehiclePhoto.objects.filter(vehicle__reference=vehicle["reference"]).count(), 0)
        output = " ".join(logs.output)
        self.assertIn("permission_denied", output)
        self.assertIn("errno=13", output)
        self.assertNotIn("private path", output)

    def test_partial_storage_failure_rolls_back_rows_and_cleans_written_objects(self):
        vehicle = self.create_vehicle("PHOTO-PARTIAL-FAIL")
        original_save = FileSystemStorage._save
        save_count = 0

        def fail_second(storage, name, content):
            nonlocal save_count
            save_count += 1
            if save_count == 2:
                raise OSError(errno.ENOSPC, "private filesystem detail")
            return original_save(storage, name, content)

        with patch.object(FileSystemStorage, "_save", autospec=True, side_effect=fail_second):
            response = self.upload(vehicle["reference"], self.image_upload("first.png", (1, 1, 1)), self.image_upload("second.png", (2, 2, 2)))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(VehiclePhoto.objects.filter(vehicle__reference=vehicle["reference"]).count(), 0)
        media_files = [path for path in Path(self.media_dir.name).rglob("*") if path.is_file()]
        self.assertEqual(media_files, [])

    def test_public_photo_access_and_missing_file_are_handled(self):
        vehicle = self.create_vehicle("PHOTO-PUBLIC", visibility="published")
        response = self.upload(vehicle["reference"], self.image_upload())
        self.assertEqual(response.status_code, 201, response.data)
        photo_id = response.data["photos"][0]["id"]
        catalogue = self.client.get("/api/cars/")
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.data[0]["photos"][0]["url"], f"/api/vehicle-photos/{photo_id}/")

        self.client.force_authenticate(user=None)
        def buffered_file_response(uploaded_file, content_type):
            try:
                return HttpResponse(uploaded_file.read(), content_type=content_type)
            finally:
                uploaded_file.close()

        with patch("accounts.views.FileResponse", side_effect=buffered_file_response):
            image_response = self.client.get(f"/api/vehicle-photos/{photo_id}/")
        self.assertEqual(image_response.status_code, 200)
        self.assertTrue(image_response["Content-Type"].startswith("image/png"))

        photo = VehiclePhoto.objects.get(pk=photo_id)
        photo.image.storage.delete(photo.image.name)
        missing = self.client.get(f"/api/vehicle-photos/{photo_id}/")
        self.assertEqual(missing.status_code, 404)

    def test_non_public_vehicle_photo_remains_hidden_from_public(self):
        vehicle = self.create_vehicle("PHOTO-PRIVATE", visibility="draft")
        response = self.upload(vehicle["reference"], self.image_upload())
        photo_id = response.data["photos"][0]["id"]
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f"/api/vehicle-photos/{photo_id}/").status_code, 404)

    def test_published_photos_are_hidden_when_vehicle_is_reserved_sold_or_archived(self):
        vehicle = self.create_vehicle("PHOTO-LIFECYCLE", visibility="published")
        response = self.upload(vehicle["reference"], self.image_upload())
        self.assertEqual(response.status_code, 201, response.data)
        photo_id = response.data["photos"][0]["id"]
        self.client.force_authenticate(user=None)
        for status_value in (Vehicle.Status.RESERVED, Vehicle.Status.SOLD, Vehicle.Status.ARCHIVED):
            with self.subTest(status=status_value):
                Vehicle.objects.filter(pk=vehicle["id"]).update(status=status_value)
                self.assertEqual(self.client.get(f"/api/vehicle-photos/{photo_id}/").status_code, 404)

    def test_eight_megabyte_and_ten_photo_limits_are_enforced(self):
        vehicle = self.create_vehicle("PHOTO-LIMITS")
        oversized = SimpleUploadedFile("large.png", b"x" * (8 * 1024 * 1024 + 1), content_type="image/png")
        too_large = self.upload(vehicle["reference"], oversized)
        self.assertEqual(too_large.status_code, 400)

        ten_photos = [self.image_upload(f"photo-{index}.png", (index, 2, 3)) for index in range(10)]
        accepted = self.upload(vehicle["reference"], *ten_photos)
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(len(accepted.data["photos"]), 10)
        overflow = self.upload(vehicle["reference"], self.image_upload("overflow.png", (255, 255, 255)))
        self.assertEqual(overflow.status_code, 400)
        self.assertEqual(VehiclePhoto.objects.filter(vehicle__reference=vehicle["reference"]).count(), 10)

