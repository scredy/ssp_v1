from io import BytesIO

from PIL import Image, ImageOps
from django.core.files.base import ContentFile


MAX_OPTIMIZED_BYTES = 500_000
MAX_IMAGE_DIMENSION = 1920
MAX_DECODED_PIXELS = 16_000_000


def optimize_vehicle_photo(upload):
    upload.seek(0)

    try:
        with Image.open(upload) as original:
            if getattr(original, "is_animated", False):
                raise ValueError("Animated vehicle photographs are not supported.")

            if original.format == "JPEG":
                original.draft("RGB", (1920, 1920))

            # Check decoded dimensions before allocating pixel buffers.
            if original.width * original.height > MAX_DECODED_PIXELS:
                raise ValueError(
                    "Image dimensions exceed the safe processing limit."
                )

            with ImageOps.exif_transpose(original) as oriented:
                oriented.thumbnail(
                    (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                    Image.Resampling.LANCZOS,
                )

                has_alpha = (
                    "A" in oriented.getbands()
                    or "transparency" in oriented.info
                )

                image = oriented.convert("RGBA" if has_alpha else "RGB")

                try:
                    image.info.clear()

                    for dimension in (1920, 1600, 1280, 960, 640):
                        image.thumbnail(
                            (dimension, dimension),
                            Image.Resampling.LANCZOS,
                        )

                        for quality in (85, 75, 65, 55):
                            with BytesIO() as output:
                                image.save(
                                    output,
                                    format="WEBP",
                                    quality=quality,
                                    method=4,
                                )

                                if output.tell() <= MAX_OPTIMIZED_BYTES:
                                    return ContentFile(
                                        output.getvalue(),
                                        name="optimized.webp",
                                    )

                    raise ValueError(
                        "Image could not be optimized below 500 KB."
                    )
                finally:
                    image.close()
    finally:
        upload.seek(0)
