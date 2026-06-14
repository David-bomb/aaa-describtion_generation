from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_products import (
    DEFAULT_CSV_PATH,
    DEFAULT_IMAGES_DIR,
    DEFAULT_SEED,
    DEFAULT_TIMEOUT_SECONDS,
    NvidiaSmiMonitor,
    ProductRow,
    load_product_rows,
    post_description,
    resolve_image_path,
    select_rows,
)


DEFAULT_URL = "http://localhost:8081/generate-description"
DEFAULT_CONCURRENCY_LEVELS = "1,2,4,8,16"
DEFAULT_REQUESTS_PER_LEVEL = 16
DEFAULT_WARMUP_REQUESTS = 2
DEFAULT_OUTPUT_PATH = Path("reports/load_test.jsonl")
DEFAULT_DOCKER_CONTAINERS = ("service-api-1", "service-qwen-vllm-1")


@dataclass(frozen=True)
class LoadTestItem:
    row: ProductRow
    image_path: Path


class DockerStatsMonitor:
    def __init__(
        self,
        containers: tuple[str, ...] = DEFAULT_DOCKER_CONTAINERS,
        interval_seconds: float = 1.0,
    ) -> None:
        self.containers = containers
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self.error: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "DockerStatsMonitor":
        if shutil.which("docker") is None:
            self.error = "docker not found"
            return self

        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 2)

    def _sample_loop(self) -> None:
        while not self._stop_event.is_set():
            self.samples.extend(self._read_samples())
            self._stop_event.wait(self.interval_seconds)

    def _read_samples(self) -> list[dict[str, Any]]:
        command = [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            *self.containers,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.error = str(exc)
            return []

        if result.returncode != 0:
            self.error = result.stderr.strip() or result.stdout.strip() or "docker stats failed"
            return []

        now = time.time()
        samples = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                self.error = f"unexpected docker stats output: {line}"
                continue

            mem_used_raw = str(raw.get("MemUsage", "")).split("/")[0].strip()
            sample = {
                "timestamp": now,
                "name": raw.get("Name") or raw.get("Container"),
                "cpu_percent": _parse_percent(str(raw.get("CPUPerc", ""))),
                "memory_used_mib": _parse_docker_size_mib(mem_used_raw),
                "memory_percent": _parse_percent(str(raw.get("MemPerc", ""))),
            }
            samples.append(sample)
        return samples

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"available": False, "samples": 0, "error": self.error}

        by_container: dict[str, list[dict[str, Any]]] = {}
        for sample in self.samples:
            by_container.setdefault(str(sample["name"]), []).append(sample)

        containers = {}
        for name, samples in by_container.items():
            cpu_values = [sample["cpu_percent"] for sample in samples if _is_number(sample["cpu_percent"])]
            mem_values = [
                sample["memory_used_mib"]
                for sample in samples
                if _is_number(sample["memory_used_mib"])
            ]
            mem_percent_values = [
                sample["memory_percent"]
                for sample in samples
                if _is_number(sample["memory_percent"])
            ]
            containers[name] = {
                "samples": len(samples),
                "peak_cpu_percent": max(cpu_values) if cpu_values else None,
                "avg_cpu_percent": round(sum(cpu_values) / len(cpu_values), 2)
                if cpu_values
                else None,
                "peak_memory_used_mib": max(mem_values) if mem_values else None,
                "avg_memory_used_mib": round(sum(mem_values) / len(mem_values), 2)
                if mem_values
                else None,
                "peak_memory_percent": max(mem_percent_values) if mem_percent_values else None,
            }

        return {
            "available": True,
            "samples": len(self.samples),
            "containers": containers,
            "error": self.error,
        }


def _parse_percent(value: str) -> float:
    try:
        return float(value.strip().removesuffix("%"))
    except ValueError:
        return float("nan")


def _parse_docker_size_mib(value: str) -> float:
    cleaned = value.strip()
    if not cleaned:
        return float("nan")

    units = {
        "b": 1 / (1024 * 1024),
        "kb": 1 / 1024,
        "kib": 1 / 1024,
        "mb": 1,
        "mib": 1,
        "gb": 1024,
        "gib": 1024,
    }
    number = ""
    unit = ""
    for char in cleaned:
        if char.isdigit() or char in {".", ","}:
            number += char.replace(",", ".")
        elif not char.isspace():
            unit += char.lower()

    try:
        parsed_number = float(number)
    except ValueError:
        return float("nan")
    return parsed_number * units.get(unit, 1)


def _is_number(value: float) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(value)


def latency_summary(latencies_ms: list[float]) -> dict[str, float | int | None]:
    if not latencies_ms:
        return {
            "count": 0,
            "min_ms": None,
            "avg_ms": None,
            "p50_ms": None,
            "p90_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
        }

    values = sorted(latencies_ms)
    return {
        "count": len(values),
        "min_ms": round(values[0], 2),
        "avg_ms": round(sum(values) / len(values), 2),
        "p50_ms": round(_percentile(values, 50), 2),
        "p90_ms": round(_percentile(values, 90), 2),
        "p95_ms": round(_percentile(values, 95), 2),
        "p99_ms": round(_percentile(values, 99), 2),
        "max_ms": round(values[-1], 2),
    }


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def parse_concurrency_levels(raw_value: str) -> list[int]:
    levels = []
    for part in raw_value.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        value = int(stripped)
        if value <= 0:
            raise ValueError("concurrency levels must be positive integers")
        levels.append(value)
    if not levels:
        raise ValueError("at least one concurrency level is required")
    return levels


def load_items(csv_path: Path, images_dir: Path, limit: int, seed: int) -> list[LoadTestItem]:
    rows = select_rows(load_product_rows(csv_path), limit=limit, seed=seed)
    items = []
    for row in rows:
        image_path = resolve_image_path(images_dir, row.image_id)
        if image_path is not None:
            items.append(LoadTestItem(row=row, image_path=image_path))
    if not items:
        raise ValueError("no rows with local images found")
    return items


def run_warmup(
    items: list[LoadTestItem],
    url: str,
    warmup_requests: int,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    records = []
    for index in range(warmup_requests):
        item = items[index % len(items)]
        started_at = time.perf_counter()
        try:
            status_code, description = post_description(
                url=url,
                row=item.row,
                image_path=item.image_path,
                timeout_seconds=timeout_seconds,
            )
            records.append(
                {
                    "record_type": "warmup",
                    "request_index": index,
                    "row_number": item.row.row_number,
                    "status": "ok",
                    "http_status": status_code,
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "description_chars": len(description),
                }
            )
        except Exception as exc:
            records.append(
                {
                    "record_type": "warmup",
                    "request_index": index,
                    "row_number": item.row.row_number,
                    "status": "error",
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "error": str(exc),
                }
            )
    return records


def run_concurrency_level(
    level: int,
    items: list[LoadTestItem],
    url: str,
    requests_per_level: int,
    timeout_seconds: int,
    resource_interval_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = []
    started_at = time.perf_counter()

    with NvidiaSmiMonitor(interval_seconds=resource_interval_seconds) as gpu_monitor:
        with DockerStatsMonitor(interval_seconds=max(resource_interval_seconds, 0.5)) as docker_monitor:
            with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
                futures = [
                    executor.submit(
                        run_single_request,
                        concurrency=level,
                        request_index=index,
                        item=items[index % len(items)],
                        url=url,
                        timeout_seconds=timeout_seconds,
                    )
                    for index in range(requests_per_level)
                ]
                for future in concurrent.futures.as_completed(futures):
                    records.append(future.result())

            duration_seconds = time.perf_counter() - started_at
            gpu_summary = gpu_monitor.summary()
            docker_summary = docker_monitor.summary()

    records.sort(key=lambda record: record["request_index"])
    successful_latencies = [
        record["latency_ms"] for record in records if record.get("status") == "ok"
    ]
    success_count = len(successful_latencies)
    error_count = len(records) - success_count

    summary = {
        "record_type": "level_summary",
        "concurrency": level,
        "requests": requests_per_level,
        "success_count": success_count,
        "error_count": error_count,
        "duration_seconds": round(duration_seconds, 2),
        "throughput_rps": round(success_count / duration_seconds, 4)
        if duration_seconds > 0
        else 0,
        "latency": latency_summary(successful_latencies),
        "gpu": gpu_summary,
        "docker": docker_summary,
    }
    return records, summary


def run_single_request(
    concurrency: int,
    request_index: int,
    item: LoadTestItem,
    url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        status_code, description = post_description(
            url=url,
            row=item.row,
            image_path=item.image_path,
            timeout_seconds=timeout_seconds,
        )
        return {
            "record_type": "request",
            "concurrency": concurrency,
            "request_index": request_index,
            "row_number": item.row.row_number,
            "item_id": item.row.item_id,
            "image_id": item.row.image_id,
            "status": "ok",
            "http_status": status_code,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "description_chars": len(description),
            "description_words": len(description.split()),
        }
    except Exception as exc:
        return {
            "record_type": "request",
            "concurrency": concurrency,
            "request_index": request_index,
            "row_number": item.row.row_number,
            "item_id": item.row.item_id,
            "image_id": item.row.image_id,
            "status": "error",
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "error": str(exc),
        }


def run_load_test(
    csv_path: Path,
    images_dir: Path,
    url: str,
    output_path: Path,
    concurrency_levels: list[int],
    requests_per_level: int,
    warmup_requests: int,
    row_limit: int,
    seed: int,
    timeout_seconds: int,
    resource_interval_seconds: float,
) -> dict[str, Any]:
    items = load_items(csv_path=csv_path, images_dir=images_dir, limit=row_limit, seed=seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.perf_counter()
    level_summaries = []

    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        metadata = {
            "record_type": "metadata",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "csv": str(csv_path),
            "images_dir": str(images_dir),
            "url": url,
            "row_limit": row_limit,
            "available_items": len(items),
            "concurrency_levels": concurrency_levels,
            "requests_per_level": requests_per_level,
            "warmup_requests": warmup_requests,
            "timeout_seconds": timeout_seconds,
        }
        output_file.write(json.dumps(metadata, ensure_ascii=False) + "\n")

        for record in run_warmup(
            items=items,
            url=url,
            warmup_requests=warmup_requests,
            timeout_seconds=timeout_seconds,
        ):
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")

        for level in concurrency_levels:
            records, summary = run_concurrency_level(
                level=level,
                items=items,
                url=url,
                requests_per_level=requests_per_level,
                timeout_seconds=timeout_seconds,
                resource_interval_seconds=resource_interval_seconds,
            )
            for record in records:
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            output_file.write(json.dumps(summary, ensure_ascii=False) + "\n")
            output_file.flush()
            level_summaries.append(summary)

        summary = {
            "record_type": "summary",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": round(time.perf_counter() - started_at, 2),
            "levels": level_summaries,
        }
        output_file.write(json.dumps(summary, ensure_ascii=False) + "\n")

    return summary


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("reports") / f"load_test_{timestamp}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run concurrent load tests against the local Avito description API."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES_DIR)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--concurrency-levels", default=DEFAULT_CONCURRENCY_LEVELS)
    parser.add_argument("--requests-per-level", type=int, default=DEFAULT_REQUESTS_PER_LEVEL)
    parser.add_argument("--warmup-requests", type=int, default=DEFAULT_WARMUP_REQUESTS)
    parser.add_argument("--row-limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--resource-interval", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = args.output or default_output_path()
    summary = run_load_test(
        csv_path=args.csv,
        images_dir=args.images_dir,
        url=args.url,
        output_path=output_path,
        concurrency_levels=parse_concurrency_levels(args.concurrency_levels),
        requests_per_level=args.requests_per_level,
        warmup_requests=args.warmup_requests,
        row_limit=args.row_limit,
        seed=args.seed,
        timeout_seconds=args.timeout,
        resource_interval_seconds=args.resource_interval,
    )
    print(json.dumps({"output": str(output_path), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
