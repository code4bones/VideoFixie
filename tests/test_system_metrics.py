import tempfile
import unittest
from pathlib import Path

from videofixie.services.system_metrics import (
    SystemMetrics,
    SystemMetricsCollector,
    format_bytes,
    parse_nvidia_gpu_percent,
    read_cpu_sample,
    read_ram_sample,
)


class SystemMetricsTest(unittest.TestCase):
    def test_reads_cpu_sample_from_proc_stat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stat_path = Path(tmp_dir) / "stat"
            stat_path.write_text("cpu  100 20 30 400 50 0 0 0 0 0\n", encoding="utf-8")

            idle, total = read_cpu_sample(stat_path) or (None, None)

        self.assertEqual(idle, 450)
        self.assertEqual(total, 600)

    def test_collector_calculates_cpu_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stat_path = Path(tmp_dir) / "stat"
            meminfo_path = Path(tmp_dir) / "meminfo"
            meminfo_path.write_text("MemTotal: 1000 kB\nMemAvailable: 250 kB\n", encoding="utf-8")
            stat_path.write_text("cpu  100 0 0 900 0 0 0 0 0 0\n", encoding="utf-8")
            collector = SystemMetricsCollector(stat_path, meminfo_path, gpu_query=lambda: 42)

            first = collector.sample()
            stat_path.write_text("cpu  150 0 0 950 0 0 0 0 0 0\n", encoding="utf-8")
            second = collector.sample()

        self.assertIsNone(first.cpu_percent)
        self.assertEqual(second.cpu_percent, 50)
        self.assertEqual(second.gpu_percent, 42)
        self.assertEqual(second.ram_used_bytes, 750 * 1024)
        self.assertEqual(second.ram_total_bytes, 1000 * 1024)

    def test_reads_ram_sample_from_meminfo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            meminfo_path = Path(tmp_dir) / "meminfo"
            meminfo_path.write_text("MemTotal: 2048 kB\nMemAvailable: 512 kB\n", encoding="utf-8")

            used, total = read_ram_sample(meminfo_path)

        self.assertEqual(used, 1536 * 1024)
        self.assertEqual(total, 2048 * 1024)

    def test_parse_nvidia_gpu_percent(self) -> None:
        self.assertEqual(parse_nvidia_gpu_percent(" 73\n 12\n"), 73)
        self.assertIsNone(parse_nvidia_gpu_percent("N/A\n"))

    def test_format_bytes_and_ram_percent(self) -> None:
        metrics = SystemMetrics(cpu_percent=None, gpu_percent=None, ram_used_bytes=8 * 1024**3, ram_total_bytes=32 * 1024**3)

        self.assertEqual(metrics.ram_percent, 25)
        self.assertEqual(format_bytes(metrics.ram_used_bytes), "8.0 GB")
        self.assertEqual(format_bytes(metrics.ram_total_bytes), "32 GB")
