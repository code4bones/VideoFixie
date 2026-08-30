from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


GpuQuery = Callable[[], int | None]


@dataclass(frozen=True)
class SystemMetrics:
    cpu_percent: int | None
    gpu_percent: int | None
    ram_used_bytes: int | None
    ram_total_bytes: int | None

    @property
    def ram_percent(self) -> int | None:
        if self.ram_used_bytes is None or self.ram_total_bytes in (None, 0):
            return None
        return round((self.ram_used_bytes / self.ram_total_bytes) * 100)


class SystemMetricsCollector:
    def __init__(
        self,
        cpu_stat_path: str | Path = "/proc/stat",
        meminfo_path: str | Path = "/proc/meminfo",
        gpu_query: GpuQuery | None = None,
    ) -> None:
        self.cpu_stat_path = Path(cpu_stat_path)
        self.meminfo_path = Path(meminfo_path)
        self.gpu_query = gpu_query or query_nvidia_gpu_percent
        self._last_cpu_sample: tuple[int, int] | None = None

    def sample(self) -> SystemMetrics:
        cpu_percent = self._sample_cpu_percent()
        ram_used, ram_total = self._sample_ram()
        return SystemMetrics(
            cpu_percent=cpu_percent,
            gpu_percent=self.gpu_query(),
            ram_used_bytes=ram_used,
            ram_total_bytes=ram_total,
        )

    def _sample_cpu_percent(self) -> int | None:
        sample = read_cpu_sample(self.cpu_stat_path)
        if sample is None:
            return None
        previous = self._last_cpu_sample
        self._last_cpu_sample = sample
        if previous is None:
            return None

        idle_delta = sample[0] - previous[0]
        total_delta = sample[1] - previous[1]
        if total_delta <= 0:
            return None
        busy_delta = max(0, total_delta - idle_delta)
        return max(0, min(100, round((busy_delta / total_delta) * 100)))

    def _sample_ram(self) -> tuple[int | None, int | None]:
        return read_ram_sample(self.meminfo_path)


def read_cpu_sample(path: str | Path = "/proc/stat") -> tuple[int, int] | None:
    try:
        first_line = Path(path).read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    parts = first_line.split()
    if not parts or parts[0] != "cpu":
        return None
    try:
        values = [int(value) for value in parts[1:]]
    except ValueError:
        return None
    if len(values) < 4:
        return None

    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return idle, total


def read_ram_sample(path: str | Path = "/proc/meminfo") -> tuple[int | None, int | None]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    values: dict[str, int] = {}
    for line in lines:
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        fields = raw_value.strip().split()
        if not fields:
            continue
        try:
            values[key] = int(fields[0]) * 1024
        except ValueError:
            continue

    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if total is None or available is None:
        return None, total
    return max(0, total - available), total


def query_nvidia_gpu_percent() -> int | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=0.5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_nvidia_gpu_percent(result.stdout)


def parse_nvidia_gpu_percent(text: str) -> int | None:
    for line in text.splitlines():
        value = line.strip()
        if not value:
            continue
        try:
            return max(0, min(100, int(value)))
        except ValueError:
            return None
    return None


def format_bytes(value: int | None) -> str:
    if value is None:
        return "N/A"
    gib = value / (1024**3)
    if gib >= 10:
        return f"{gib:.0f} GB"
    return f"{gib:.1f} GB"
