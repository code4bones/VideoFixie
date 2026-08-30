from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import ProcessingJob, ProcessingStage
from videofixie.jobs.runner import StageRunResult

MEDIA_VALIDATION_LABEL = "Validate media output"


def build_media_validation_stage(
    media_path: str | Path,
    ffmpeg_path: str | None = None,
    max_seconds: float | None = None,
) -> ProcessingStage:
    args: list[str] = [
        "-v",
        "error",
        "-xerror",
        "-i",
        str(media_path),
    ]
    if max_seconds is not None:
        args.extend(("-t", f"{max_seconds:.3f}"))
    args.extend(("-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"))
    command = PlannedCommand(
        program=ffmpeg_path or "ffmpeg",
        args=tuple(args),
        label=MEDIA_VALIDATION_LABEL,
    )
    return ProcessingStage(MEDIA_VALIDATION_LABEL, command)


def media_validation_ffmpeg_path(job: ProcessingJob) -> str:
    for stage in job.stages:
        program_name = Path(stage.command.program).name.lower()
        if "ffmpeg" in program_name and "ffprobe" not in program_name:
            return stage.command.program
    return "ffmpeg"


def missing_media_validation_result(stage: ProcessingStage, media_path: str | Path) -> StageRunResult:
    path = Path(media_path)
    return StageRunResult(
        label=stage.label,
        command=stage.command,
        exit_code=-1,
        runtime_error=f"Output file was not created: {path}",
    )


def apply_media_validation_error(stage: ProcessingStage, result: StageRunResult, media_path: str | Path) -> StageRunResult:
    if result.succeeded or result.cancelled or result.runtime_error:
        return result
    detail = _validation_detail(result)
    return replace(
        result,
        runtime_error=f"Output media validation failed for {Path(media_path).name}: {detail}",
    )


def _validation_detail(result: StageRunResult) -> str:
    lines = tuple(line for line in (*result.stderr, *result.stdout) if line.strip())
    if lines:
        detail = " | ".join(lines[-4:])
        return detail[:500]
    return f"ffmpeg exited with code {result.exit_code}"
