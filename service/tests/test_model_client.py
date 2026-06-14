import json
import unittest
from unittest.mock import patch

from app.config import Settings
from app.model_client import VLLMClient, clean_description


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class ModelClientTests(unittest.TestCase):
    def test_clean_description_removes_common_prefix_and_collapses_spaces(self) -> None:
        self.assertEqual(clean_description("  Описание:  Красный велосипед. \n "), "Красный велосипед.")

    def test_clean_description_drops_photo_source_sentences(self) -> None:
        self.assertEqual(
            clean_description(
                "Смартфон Apple iPhone 13, память 128 ГБ. На фото виден синий корпус."
            ),
            "Смартфон Apple iPhone 13, память 128 ГБ.",
        )

    def test_generate_sends_openai_compatible_multimodal_payload(self) -> None:
        settings = Settings(
            model_id="Qwen/Qwen3-VL-4B-Instruct",
            openai_base_url="http://localhost:8000/v1",
            api_key="token",
            http_timeout_seconds=5,
            generation_max_tokens=180,
            generation_temperature=0.2,
            generation_top_p=0.8,
            image_max_bytes=1024,
        )
        client = VLLMClient(settings)
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {"choices": [{"message": {"content": "Описание: Белый корпус, состояние б/у."}}]}
            )

        with patch("urllib.request.urlopen", fake_urlopen):
            result = client.generate(prompt="Сделай описание", image_data_url="data:image/png;base64,abc")

        self.assertEqual(result, "Белый корпус, состояние б/у.")
        self.assertEqual(captured["url"], "http://localhost:8000/v1/chat/completions")
        self.assertEqual(captured["timeout"], 5)
        self.assertIn("Bearer token", captured["headers"]["Authorization"])
        body = captured["body"]
        self.assertEqual(body["model"], "Qwen/Qwen3-VL-4B-Instruct")
        self.assertEqual(body["max_tokens"], 180)
        self.assertEqual(body["messages"][0]["content"][0]["type"], "image_url")
        self.assertEqual(body["messages"][0]["content"][1]["text"], "Сделай описание")


if __name__ == "__main__":
    unittest.main()
