import unittest

from scripts.load_test import (
    _parse_docker_size_mib,
    latency_summary,
    parse_concurrency_levels,
)


class LoadTestHelpersTests(unittest.TestCase):
    def test_parse_concurrency_levels(self) -> None:
        self.assertEqual(parse_concurrency_levels("1, 2,4"), [1, 2, 4])

        with self.assertRaises(ValueError):
            parse_concurrency_levels("0")

    def test_latency_summary(self) -> None:
        summary = latency_summary([100.0, 200.0, 300.0, 400.0])

        self.assertEqual(summary["count"], 4)
        self.assertEqual(summary["min_ms"], 100.0)
        self.assertEqual(summary["avg_ms"], 250.0)
        self.assertEqual(summary["p50_ms"], 250.0)
        self.assertEqual(summary["max_ms"], 400.0)

    def test_parse_docker_size_mib(self) -> None:
        self.assertAlmostEqual(_parse_docker_size_mib("512MiB"), 512)
        self.assertAlmostEqual(_parse_docker_size_mib("1.5GiB"), 1536)
        self.assertAlmostEqual(_parse_docker_size_mib("1024KiB"), 1)


if __name__ == "__main__":
    unittest.main()
