import json
import unittest

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal local envs
    TestClient = None


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
)


class FakeModelClient:
    def ready(self) -> bool:
        return True

    def generate(self, prompt: str, image_data_url: str) -> str:
        return "Белый корпус, состояние б/у, память 128 ГБ."


@unittest.skipIf(TestClient is None, "fastapi test dependencies are not installed")
class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.main import app, get_model_client

        self.app = app
        self.get_model_client = get_model_client
        self.app.dependency_overrides[get_model_client] = lambda: FakeModelClient()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready(self) -> None:
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ready": True})

    def test_generate_description(self) -> None:
        response = self.client.post(
            "/generate-description",
            data={
                "title": "iPhone 13 128 ГБ",
                "category_name": "Телефоны",
                "params": json.dumps({"состояние": "б/у", "память": "128 ГБ"}),
            },
            files={"image": ("item.png", PNG_BYTES, "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"description": "Белый корпус, состояние б/у, память 128 ГБ."},
        )


if __name__ == "__main__":
    unittest.main()
