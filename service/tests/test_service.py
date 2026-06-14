import unittest

from app.config import Settings
from app.service import DescriptionService


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
)


class FakeModelClient:
    def __init__(self) -> None:
        self.prompt = ""
        self.image_data_url = ""

    def generate(self, prompt: str, image_data_url: str) -> str:
        self.prompt = prompt
        self.image_data_url = image_data_url
        return "Смартфон Apple iPhone, состояние б/у, память 128 ГБ."


class DescriptionServiceTests(unittest.TestCase):
    def test_generate_description_builds_prompt_and_image_data_url(self) -> None:
        client = FakeModelClient()
        service = DescriptionService(
            settings=Settings(image_max_bytes=1024),
            model_client=client,
        )

        result = service.generate_description(
            image_bytes=PNG_BYTES,
            image_content_type="image/png",
            title="iPhone 13 128 ГБ",
            category_name="Телефоны",
            params={"состояние": "б/у", "память": "128 ГБ"},
        )

        self.assertEqual(result, "Смартфон Apple iPhone, состояние б/у, память 128 ГБ.")
        self.assertTrue(client.image_data_url.startswith("data:image/png;base64,"))
        self.assertIn("iPhone 13 128 ГБ", client.prompt)
        self.assertIn('"память": "128 ГБ"', client.prompt)

    def test_generate_description_requires_title(self) -> None:
        service = DescriptionService(settings=Settings(), model_client=FakeModelClient())

        with self.assertRaises(ValueError):
            service.generate_description(
                image_bytes=PNG_BYTES,
                image_content_type="image/png",
                title=" ",
                category_name="Телефоны",
                params={},
            )


if __name__ == "__main__":
    unittest.main()
