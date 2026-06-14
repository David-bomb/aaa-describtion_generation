import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import evaluate_products


JPEG_BYTES = b"\xff\xd8\xff\xd9"


class FakeHTTPResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.status_code = status_code

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload

    def getcode(self) -> int:
        return self.status_code


class FakeGpuMonitor:
    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.interval_seconds = interval_seconds

    def __enter__(self) -> "FakeGpuMonitor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def summary(self) -> dict:
        return {"available": False, "samples": 0, "error": "disabled in test"}


class EvaluateProductsTests(unittest.TestCase):
    def test_load_product_rows_parses_required_columns_and_params(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "valid_with_params.csv"
            csv_path.write_text(
                "item_id,image_id,title,category_name,params\n"
                '1,42,"Ремешок Garmin","Личные вещи","{""цвет"": ""Красный""}"\n',
                encoding="utf-8",
            )

            rows = evaluate_products.load_product_rows(csv_path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].item_id, "1")
        self.assertEqual(rows[0].image_id, "42")
        self.assertEqual(rows[0].title, "Ремешок Garmin")
        self.assertEqual(rows[0].category_name, "Личные вещи")
        self.assertEqual(rows[0].params, {"цвет": "Красный"})

    def test_resolve_image_path_finds_image_id_jpg(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            images_dir = Path(temp_dir)
            image_path = images_dir / "42.jpg"
            image_path.write_bytes(JPEG_BYTES)

            resolved = evaluate_products.resolve_image_path(images_dir, "42")

        self.assertEqual(resolved, image_path)

    def test_missing_image_is_skipped_not_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "valid_with_params.csv"
            images_dir = temp_path / "images"
            output_path = temp_path / "report.jsonl"
            images_dir.mkdir()
            csv_path.write_text(
                "item_id,image_id,title,category_name,params\n"
                '1,missing,"Ремешок Garmin","Личные вещи","{""цвет"": ""Красный""}"\n',
                encoding="utf-8",
            )

            with patch("scripts.evaluate_products.NvidiaSmiMonitor", FakeGpuMonitor):
                summary = evaluate_products.run_evaluation(
                    csv_path=csv_path,
                    images_dir=images_dir,
                    url="http://localhost:8081/generate-description",
                    output_path=output_path,
                    limit=0,
                    seed=42,
                    timeout_seconds=5,
                    gpu_interval_seconds=0.01,
                )

            records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(summary["totals"]["skipped_count"], 1)
        self.assertEqual(summary["totals"]["total_requests"], 0)
        self.assertEqual(summary["totals"]["failed_count"], 0)
        self.assertEqual(records[0]["status"], "missing_image")
        self.assertEqual(records[-1]["record_type"], "summary")

    def test_post_description_sends_utf8_multipart_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "42.jpg"
            image_path.write_bytes(JPEG_BYTES)
            row = evaluate_products.ProductRow(
                row_number=2,
                item_id="1",
                image_id="42",
                title="Ремешок Garmin",
                category_name="Личные вещи",
                params={"цвет": "Красный"},
            )
            captured = {}

            def fake_urlopen(request, timeout):
                captured["url"] = request.full_url
                captured["timeout"] = timeout
                captured["content_type"] = request.get_header("Content-type")
                captured["body"] = request.data
                return FakeHTTPResponse({"description": "Ремешок Garmin, цвет красный."})

            with patch("urllib.request.urlopen", fake_urlopen):
                status_code, description = evaluate_products.post_description(
                    url="http://localhost:8081/generate-description",
                    row=row,
                    image_path=image_path,
                    timeout_seconds=7,
                )

        self.assertEqual(status_code, 200)
        self.assertEqual(description, "Ремешок Garmin, цвет красный.")
        self.assertEqual(captured["url"], "http://localhost:8081/generate-description")
        self.assertEqual(captured["timeout"], 7)
        self.assertIn("multipart/form-data", captured["content_type"])
        self.assertIn(b'name="title"', captured["body"])
        self.assertIn("Ремешок Garmin".encode("utf-8"), captured["body"])
        self.assertIn(b'name="category_name"', captured["body"])
        self.assertIn(b'name="params"', captured["body"])
        self.assertIn('{"цвет":"Красный"}'.encode("utf-8"), captured["body"])
        self.assertIn(b'name="image"; filename="42.jpg"', captured["body"])

    def test_validate_description_checks_length_and_forbidden_source_phrases(self) -> None:
        checks = evaluate_products.validate_description(
            "Смартфон Apple, память 128 ГБ. На фото видно синий корпус.",
            title="iPhone 13",
        )
        long_checks = evaluate_products.validate_description(
            " ".join(["слово"] * 71),
            title="Короткий заголовок",
        )

        self.assertFalse(checks["no_forbidden_source_phrases"])
        self.assertFalse(checks["passed"])
        self.assertEqual(long_checks["word_count"], 71)
        self.assertFalse(long_checks["within_70_words"])
        self.assertFalse(long_checks["passed"])

    def test_validate_description_flags_exact_title_as_first_phrase_only(self) -> None:
        exact_title_checks = evaluate_products.validate_description(
            "iPhone 13 128 ГБ, состояние б/у.",
            title="iPhone 13 128 ГБ",
        )
        natural_start_checks = evaluate_products.validate_description(
            "Стартер бренда Japanparts, модель MTD216.",
            title="Стартер",
        )

        self.assertFalse(
            exact_title_checks["does_not_repeat_exact_title_as_first_phrase"]
        )
        self.assertFalse(exact_title_checks["passed"])
        self.assertTrue(
            natural_start_checks["does_not_repeat_exact_title_as_first_phrase"]
        )
        self.assertTrue(natural_start_checks["passed"])


if __name__ == "__main__":
    unittest.main()
