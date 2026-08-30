from __future__ import annotations

import subprocess
from pathlib import Path

from videofixie.domain.commands import PlannedCommand


VAPOURSYNTH_IMPORT_PROBE = (
    "from vapoursynth import core\n"
    "text = str(core).strip().splitlines()\n"
    "print(text[0] if text else 'VapourSynth import ok')\n"
)


class VapourSynthAdapter:
    def __init__(self, python_path: str | Path) -> None:
        self.python_path = str(python_path)

    def build_import_probe_command(self) -> PlannedCommand:
        return PlannedCommand(
            self.python_path,
            ("-c", VAPOURSYNTH_IMPORT_PROBE),
            "Detect VapourSynth Python runtime",
        )

    def version(self, timeout_seconds: float = 10.0) -> str | None:
        result = subprocess.run(
            self.build_import_probe_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return parse_vapoursynth_version(result.stdout)


def parse_vapoursynth_version(text: str) -> str | None:
    return _first_line(text)


def parse_vspipe_version(text: str) -> str | None:
    return _first_line(text)


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None
