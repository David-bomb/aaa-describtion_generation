import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return int(raw_value)


def _get_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return float(raw_value)


@dataclass(frozen=True)
class Settings:
    model_id: str = "Qwen/Qwen3-VL-4B-Instruct"
    openai_base_url: str = "http://localhost:8000/v1"
    api_key: str = ""
    http_timeout_seconds: int = 120
    generation_max_tokens: int = 180
    generation_temperature: float = 0.2
    generation_top_p: float = 0.8
    image_max_bytes: int = 10 * 1024 * 1024


def load_settings() -> Settings:
    return Settings(
        model_id=os.getenv("QWEN_MODEL_ID", Settings.model_id),
        openai_base_url=os.getenv("QWEN_OPENAI_BASE_URL", Settings.openai_base_url),
        api_key=os.getenv("QWEN_API_KEY", Settings.api_key),
        http_timeout_seconds=_get_int(
            "VLLM_HTTP_TIMEOUT_SECONDS", Settings.http_timeout_seconds
        ),
        generation_max_tokens=_get_int(
            "GENERATION_MAX_TOKENS", Settings.generation_max_tokens
        ),
        generation_temperature=_get_float(
            "GENERATION_TEMPERATURE", Settings.generation_temperature
        ),
        generation_top_p=_get_float("GENERATION_TOP_P", Settings.generation_top_p),
        image_max_bytes=_get_int("IMAGE_MAX_BYTES", Settings.image_max_bytes),
    )
