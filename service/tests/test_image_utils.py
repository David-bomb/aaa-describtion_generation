import base64
import unittest

from app.image_utils import image_bytes_to_data_url


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAF"
    "gwJ/lwVxWQAAAABJRU5ErkJggg=="
)


class ImageUtilsTests(unittest.TestCase):
    def test_image_bytes_to_data_url_detects_png(self) -> None:
        data_url = image_bytes_to_data_url(TINY_PNG, content_type=None, max_bytes=1024)

        self.assertTrue(data_url.startswith("data:image/png;base64,"))

    def test_image_bytes_to_data_url_rejects_oversized_image(self) -> None:
        with self.assertRaises(ValueError):
            image_bytes_to_data_url(TINY_PNG, content_type="image/png", max_bytes=10)

    def test_image_bytes_to_data_url_rejects_unknown_type(self) -> None:
        with self.assertRaises(ValueError):
            image_bytes_to_data_url(b"not an image", content_type=None, max_bytes=1024)


if __name__ == "__main__":
    unittest.main()
