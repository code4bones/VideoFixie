from __future__ import annotations

from dataclasses import replace

from videofixie.backends.video2x import VIDEO2X_PROCESSING_LABEL, detect_runtime_error
from videofixie.domain.jobs import ProcessingStage
from videofixie.jobs.runner import StageRunResult


def apply_backend_runtime_error(stage: ProcessingStage, result: StageRunResult) -> StageRunResult:
    if stage.command.label != VIDEO2X_PROCESSING_LABEL:
        return result
    runtime_error = detect_runtime_error(result.stdout, result.stderr)
    if runtime_error is None:
        return result
    return replace(result, runtime_error=runtime_error)
