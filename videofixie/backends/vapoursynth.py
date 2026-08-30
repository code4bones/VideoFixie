from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import GeneratedFile, JobProgress
from videofixie.domain.profiles import ProcessingProfile


VAPOURSYNTH_IMPORT_PROBE = (
    "from vapoursynth import core\n"
    "text = str(core).strip().splitlines()\n"
    "print(text[0] if text else 'VapourSynth import ok')\n"
)
PROGRESS_RE = re.compile(r"Frame:\s*(?P<current>\d+)\s*/\s*(?P<total>\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class VapourSynthRenderPlan:
    script: GeneratedFile
    y4m_path: Path
    command: PlannedCommand


class VapourSynthAdapter:
    def __init__(self, python_path: str | Path, vspipe_path: str | Path = "vspipe") -> None:
        self.python_path = str(python_path)
        self.vspipe_path = str(vspipe_path)

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

    def build_render_plan(
        self,
        source_path: str | Path,
        script_path: str | Path,
        y4m_path: str | Path,
        profile: ProcessingProfile,
    ) -> VapourSynthRenderPlan:
        script = GeneratedFile(
            path=Path(script_path),
            content=build_preview_script(source_path, profile),
            description="VapourSynth script",
        )
        command = PlannedCommand(
            self.vspipe_path,
            ("--progress", "-c", "y4m", str(script.path), str(y4m_path)),
            "Run VapourSynth script",
        )
        return VapourSynthRenderPlan(script=script, y4m_path=Path(y4m_path), command=command)


def build_preview_script(source_path: str | Path, profile: ProcessingProfile) -> str:
    filter_name = _filter_name(profile)
    scale = profile.scale or 1
    source_literal = repr(str(source_path))
    return "\n".join(
        (
            "import vapoursynth as vs",
            "core = vs.core",
            f"clip = core.bs.VideoSource({source_literal})",
            f"width = clip.width * {scale}",
            f"height = clip.height * {scale}",
            f"clip = core.resize.{filter_name}(clip, width=width, height=height, format=vs.YUV420P8)",
            "clip.set_output()",
            "",
        )
    )


def parse_progress_line(line: str) -> JobProgress | None:
    match = PROGRESS_RE.search(line)
    if not match:
        return None

    current = int(match.group("current"))
    total = int(match.group("total"))
    return JobProgress(
        current_frame=current,
        total_frames=total,
        percent=(current / total * 100.0) if total else None,
    )


def parse_vapoursynth_version(text: str) -> str | None:
    return _first_line(text)


def parse_vspipe_version(text: str) -> str | None:
    return _first_line(text)


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def _filter_name(profile: ProcessingProfile) -> str:
    filters = {
        "builtin-lanczos": "Lanczos",
        "builtin-bicubic": "Bicubic",
    }
    try:
        return filters[profile.model]
    except KeyError as exc:
        raise ValueError(f"Unsupported VapourSynth profile model: {profile.model}") from exc
