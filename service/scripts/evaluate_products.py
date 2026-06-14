from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import subprocess
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_CSV_PATH = Path("data/valid_with_params.csv")
DEFAULT_IMAGES_DIR = Path("data/AAA_1image_dataset_images")
DEFAULT_URL = "http://localhost:8081/generate-description"
DEFAULT_LIMIT = 20
DEFAULT_SEED = 42
DEFAULT_TIMEOUT_SECONDS = 180

REQUIRED_COLUMNS = {"image_id", "title", "category_name", "params"}
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
FORBIDDEN_SOURCE_PATTERNS = (
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


@dataclass(frozen=True)
class ProductRow:
    row_number: int
    item_id: str
    image_id: str
    title: str
    category_name: str
    params: dict[str, Any]


class NvidiaSmiMonitor:
    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, float]] = []
        self.error: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "NvidiaSmiMonitor":
        if shutil.which("nvidia-smi") is None:
            self.error = "nvidia-smi not found"
            return self

        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 1)

    def _sample_loop(self) -> None:
        while not self._stop_event.is_set():
            sample = self._read_sample()
            if sample is not None:
                self.samples.append(sample)
            self._stop_event.wait(self.interval_seconds)

    def _read_sample(self) -> dict[str, float] | None:
        command = [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total,power.draw",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.error = str(exc)
            return None

        if result.returncode != 0:
            self.error = result.stderr.strip() or result.stdout.strip() or "nvidia-smi failed"
            return None

        first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
        values = [value.strip() for value in first_line.split(",")]
        if len(values) < 4:
            self.error = f"unexpected nvidia-smi output: {first_line}"
            return None

        return {
            "timestamp": time.time(),
            "gpu_utilization_percent": _parse_float(values[0]),
            "memory_used_mib": _parse_float(values[1]),
            "memory_total_mib": _parse_float(values[2]),
            "power_draw_watts": _parse_float(values[3]),
        }

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"available": False, "samples": 0, "error": self.error}

        gpu_values = [sample["gpu_utilization_percent"] for sample in self.samples]
        memory_values = [sample["memory_used_mib"] for sample in self.samples]
        total_memory_values = [sample["memory_total_mib"] for sample in self.samples]
        power_values = [
            sample["power_draw_watts"]
            for sample in self.samples
            if sample["power_draw_watts"] == sample["power_draw_watts"]
        ]

        return {
            "available": True,
            "samples": len(self.samples),
            "peak_gpu_utilization_percent": max(gpu_values),
            "avg_gpu_utilization_percent": round(sum(gpu_values) / len(gpu_values), 2),
            "peak_memory_used_mib": max(memory_values),
            "memory_total_mib": max(total_memory_values),
            "peak_power_draw_watts": max(power_values) if power_values else None,
            "avg_power_draw_watts": round(sum(power_values) / len(power_values), 2)
            if power_values
            else None,
            "error": self.error,
        }


def _parse_float(raw_value: str) -> float:
    try:
        return float(raw_value)
    except ValueError:
        return float("nan")


def load_product_rows(csv_path: Path) -> list[ProductRow]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - fieldnames
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"CSV is missing required columns: {missing}")

        rows = []
        for row_number, raw_row in enumerate(reader, start=2):
            rows.append(
                ProductRow(
                    row_number=row_number,
                    item_id=(raw_row.get("item_id") or "").strip(),
                    image_id=(raw_row.get("image_id") or "").strip(),
                    title=(raw_row.get("title") or "").strip(),
                    category_name=(raw_row.get("category_name") or "").strip(),
                    params=parse_params(raw_row.get("params") or "{}", row_number=row_number),
                )
            )
        return rows


def parse_params(raw_params: str, row_number: int) -> dict[str, Any]:
    if not raw_params.strip():
        return {}

    try:
        parsed = json.loads(raw_params)
    except json.JSONDecodeError as exc:
        raise ValueError(f"row {row_number}: params must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"row {row_number}: params must be a JSON object")

    return parsed


def resolve_image_path(images_dir: Path, image_id: str) -> Path | None:
    if not image_id:
        return None

    for extension in IMAGE_EXTENSIONS:
        candidate = images_dir / f"{image_id}{extension}"
        if candidate.is_file():
            return candidate
    return None


def select_rows(rows: list[ProductRow], limit: int, seed: int) -> list[ProductRow]:
    if limit < 0:
        raise ValueError("limit must be 0 or greater")
    if limit == 0 or limit >= len(rows):
        return list(rows)

    rng = random.Random(seed)
    return rng.sample(rows, limit)


def post_description(
    url: str,
    row: ProductRow,
    image_path: Path,
    timeout_seconds: int,
) -> tuple[int, str]:
    params_json = json.dumps(row.params, ensure_ascii=False, separators=(",", ":"))
    fields = {
        "title": row.title,
        "category_name": row.category_name,
        "params": params_json,
    }
    body, content_type = encode_multipart_formdata(
        fields=fields,
        file_field_name="image",
        file_path=image_path,
    )
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            description = payload.get("description")
            if not isinstance(description, str):
                raise ValueError("response JSON does not contain string field 'description'")
            return response.getcode(), description
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("response is not valid JSON") from exc


def encode_multipart_formdata(
    fields: dict[str, str],
    file_field_name: str,
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = f"avito-qwen-{uuid.uuid4().hex}"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode("ascii"))
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        parts.append(value.encode("utf-8"))
        parts.append(b"\r\n")

    parts.append(f"--{boundary}\r\n".encode("ascii"))
    parts.append(
        (
            f'Content-Disposition: form-data; name="{file_field_name}"; '
            f'filename="{file_path.name}"\r\n'
        ).encode("utf-8")
    )
    parts.append(f"Content-Type: {_guess_content_type(file_path)}\r\n\r\n".encode("ascii"))
    parts.append(file_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("ascii"))

    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _guess_content_type(image_path: Path) -> str:
    extension = image_path.suffix.lower()
    if extension in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if extension == ".webp":
        return "image/webp"
    return "image/png"


def validate_description(description: str, title: str) -> dict[str, Any]:
    normalized_description = " ".join(description.split())
    normalized_title = " ".join(title.split()).casefold()
    lowered_description = normalized_description.casefold()
    first_phrase = _extract_first_phrase(lowered_description)
    word_count = len(normalized_description.split())

    checks = {
        "non_empty": bool(normalized_description),
        "word_count": word_count,
        "within_70_words": word_count <= 70,
        "no_forbidden_source_phrases": not any(
            pattern in lowered_description for pattern in FORBIDDEN_SOURCE_PATTERNS
        ),
        "no_markdown": not _contains_markdown(normalized_description),
        "no_emoji": not _contains_emoji(normalized_description),
        "does_not_repeat_exact_title_as_first_phrase": first_phrase != normalized_title,
    }
    checks["passed"] = all(value for key, value in checks.items() if key != "word_count")
    return checks


def _extract_first_phrase(text: str) -> str:
    phrase_end = len(text)
    for separator in (".", "!", "?", ",", ";", ":"):
        position = text.find(separator)
        if position != -1:
            phrase_end = min(phrase_end, position)
    return text[:phrase_end].strip()


def _contains_markdown(text: str) -> bool:
    stripped = text.strip()
    return (
        stripped.startswith("#")
        or stripped.startswith("- ")
        or stripped.startswith("* ")
        or "`" in stripped
        or "**" in stripped
    )


def _contains_emoji(text: str) -> bool:
    return any(
        0x1F300 <= ord(char) <= 0x1FAFF or 0x2600 <= ord(char) <= 0x27BF for char in text
    )


def run_evaluation(
    csv_path: Path,
    images_dir: Path,
    url: str,
    output_path: Path,
    limit: int,
    seed: int,
    timeout_seconds: int,
    gpu_interval_seconds: float = 0.5,
) -> dict[str, Any]:
    rows = select_rows(load_product_rows(csv_path), limit=limit, seed=seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    totals = {
        "total_requests": 0,
        "success_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "quality_failed_count": 0,
    }

    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        with NvidiaSmiMonitor(interval_seconds=gpu_interval_seconds) as gpu_monitor:
            for row in rows:
                record = evaluate_row(
                    row=row,
                    images_dir=images_dir,
                    url=url,
                    timeout_seconds=timeout_seconds,
                )
                update_totals(totals, record)
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                output_file.flush()

            summary = {
                "record_type": "summary",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "csv": str(csv_path),
                "images_dir": str(images_dir),
                "url": url,
                "limit": limit,
                "seed": seed,
                "totals": totals,
                "gpu": gpu_monitor.summary(),
            }
            output_file.write(json.dumps(summary, ensure_ascii=False) + "\n")

    return summary


def evaluate_row(
    row: ProductRow,
    images_dir: Path,
    url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    base_record: dict[str, Any] = {
        "record_type": "item",
        "row_number": row.row_number,
        "item_id": row.item_id,
        "image_id": row.image_id,
        "title": row.title,
        "category_name": row.category_name,
    }
    image_path = resolve_image_path(images_dir, row.image_id)
    if image_path is None:
        return {
            **base_record,
            "status": "missing_image",
            "success": False,
            "skipped": True,
            "error": f"image file not found for image_id={row.image_id}",
        }

    start_time = time.perf_counter()
    try:
        status_code, description = post_description(
            url=url,
            row=row,
            image_path=image_path,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            **base_record,
            "status": "error",
            "success": False,
            "skipped": False,
            "image_path": str(image_path),
            "latency_ms": latency_ms,
            "error": str(exc),
        }

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    checks = validate_description(description=description, title=row.title)
    return {
        **base_record,
        "status": "ok",
        "success": True,
        "skipped": False,
        "image_path": str(image_path),
        "http_status": status_code,
        "latency_ms": latency_ms,
        "description": description,
        "checks": checks,
    }


def update_totals(totals: dict[str, int], record: dict[str, Any]) -> None:
    if record.get("skipped"):
        totals["skipped_count"] += 1
        return

    totals["total_requests"] += 1
    if record.get("success"):
        totals["success_count"] += 1
        checks = record.get("checks") or {}
        if not checks.get("passed", False):
            totals["quality_failed_count"] += 1
    else:
        totals["failed_count"] += 1


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("reports") / f"eval_{timestamp}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the local Avito description API on real product rows."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES_DIR)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--gpu-interval", type=float, default=0.5)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = args.output or default_output_path()
    summary = run_evaluation(
        csv_path=args.csv,
        images_dir=args.images_dir,
        url=args.url,
        output_path=output_path,
        limit=args.limit,
        seed=args.seed,
        timeout_seconds=args.timeout,
        gpu_interval_seconds=args.gpu_interval,
    )
    print(json.dumps({"output": str(output_path), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
