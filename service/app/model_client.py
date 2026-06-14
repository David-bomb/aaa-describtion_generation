import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.config import Settings


class ModelClientError(RuntimeError):
    pass


_FORBIDDEN_SOURCE_PATTERNS = (
    "на фото",
    "по описанию",
    "указано",
    "указаны",
    "видно",
    "виден",
    "видна",
    "видны",
    "лежит",
    "стоит",
    "держат в руках",
)


def clean_description(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"^(описание|description)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = _drop_forbidden_source_sentences(cleaned)
    return cleaned.strip(" \t\r\n\"'")


def _drop_forbidden_source_sentences(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept_sentences = []

    for sentence in sentences:
        lowered = sentence.lower()
        if any(pattern in lowered for pattern in _FORBIDDEN_SOURCE_PATTERNS):
            continue
        kept_sentences.append(sentence)

    return " ".join(kept_sentences).strip()


class VLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.openai_base_url.rstrip("/")

    def ready(self) -> bool:
        request = urllib.request.Request(
            f"{self.base_url}/models",
            headers=self._headers(),
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=min(self.settings.http_timeout_seconds, 10),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return False

        models = payload.get("data", [])
        return any(model.get("id") == self.settings.model_id for model in models)

    def generate(self, prompt: str, image_data_url: str) -> str:
        payload = {
            "model": self.settings.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": self.settings.generation_max_tokens,
            "temperature": self.settings.generation_temperature,
            "top_p": self.settings.generation_top_p,
        }

        response_payload = self._post_json("/chat/completions", payload)
        try:
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelClientError("model response has unexpected format") from exc

        if not isinstance(content, str) or not content.strip():
            raise ModelClientError("model returned empty description")

        return clean_description(content)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.http_timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ModelClientError(f"model backend returned HTTP {exc.code}: {detail}") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise ModelClientError(f"model backend is unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ModelClientError("model backend returned invalid JSON") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers
