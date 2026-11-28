from io import BytesIO
from random import Random

from PIL import Image
from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from .image_optimizer import (
    optimize_vehicle_photo,
    MAX_OPTIMIZED_BYTES,
)


class ImageOptimizerTests(SimpleTestCase):
    def make_upload(self, mode="RGB", size=(2400, 1600)):
        color = (120, 80, 40, 100) if mode == "RGBA" else (120, 80, 40)

        with Image.new(mode, size, color) as image:
            with BytesIO() as output:
                image.save(output, format="PNG")
                return ContentFile(
                    output.getvalue(),
                    name="test.png",
                )

    def test_image_is_converted_to_webp(self):
        upload = self.make_upload()
        optimized = optimize_vehicle_photo(upload)

        with Image.open(optimized) as result:
            self.assertEqual(result.format, "WEBP")
            self.assertEqual(result.size, (1920, 1280))

        self.assertLessEqual(
            optimized.size,
            MAX_OPTIMIZED_BYTES,
        )
        self.assertEqual(upload.tell(), 0)

    def test_transparent_images_preserve_alpha(self):
        optimized = optimize_vehicle_photo(
            self.make_upload("RGBA", (800, 600))
        )

        with Image.open(optimized) as result:
            self.assertEqual(result.mode, "RGBA")
            self.assertEqual(result.size, (800, 600))

    def test_high_detail_image_stays_within_size_limit(self):
        pixels = Random(42).randbytes(1920 * 1080 * 3)

        with Image.frombytes("RGB", (1920, 1080), pixels) as image:
            with BytesIO() as output:
                image.save(output, format="PNG")
                upload = ContentFile(output.getvalue(), name="detail.png")

        optimized = optimize_vehicle_photo(upload)

        self.assertLessEqual(
            optimized.size,
            MAX_OPTIMIZED_BYTES,
        )

        with Image.open(optimized) as result:
            result.verify()

    def test_small_images_are_not_enlarged(self):
        optimized = optimize_vehicle_photo(
            self.make_upload(size=(640, 480))
        )

        with Image.open(optimized) as result:
            self.assertEqual(result.size, (640, 480))

    def test_invalid_image_is_rejected(self):
        upload = ContentFile(b"not an image", name="invalid.png")

        with self.assertRaises(OSError):
            optimize_vehicle_photo(upload)

    def test_exif_orientation_applied_and_metadata_removed(self):
        with Image.new("RGB", (120, 80), "red") as image:
            exif = Image.Exif()
            exif[274] = 6
            exif[270] = "Private test metadata"

            with BytesIO() as output:
                image.save(output, format="JPEG", exif=exif)
                upload = ContentFile(output.getvalue(), name="rotated.jpg")

        optimized = optimize_vehicle_photo(upload)

        with Image.open(optimized) as result:
            self.assertEqual(result.size, (80, 120))
            self.assertNotIn("exif", result.info)

    def test_oversized_decoded_image_is_rejected(self):
        from unittest.mock import patch, MagicMock

        upload = ContentFile(b"test", name="large.png")

        image = MagicMock()
        image.format = "PNG"
        image.is_animated = False
        image.width = 5000
        image.height = 5000

        with patch(
            "accounts.image_optimizer.Image.open"
        ) as mocked_open:
            mocked_open.return_value.__enter__.return_value = image

            with patch(
                "accounts.image_optimizer.ImageOps.exif_transpose"
            ) as transpose:
                with self.assertRaises(ValueError):
                    optimize_vehicle_photo(upload)

                transpose.assert_not_called()
