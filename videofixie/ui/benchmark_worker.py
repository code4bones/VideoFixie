from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from videofixie.jobs.runner import CancellationToken, JobRunResult, ProcessLogLine, SubprocessJobRunner
from videofixie.services.app import PlannedVideo2XBenchmark
from videofixie.ui.preview_worker import _parse_preview_progress_line, _stage_display, successful_output_path


@dataclass(frozen=True)
class BenchmarkVariantRun:
    index: int
    output_path: Path | None
    result: JobRunResult
    error: str | None = None


class BenchmarkWorker(QObject):
    variantStarted = Signal(int, str)
    stageStarted = Signal(int, str, str)
    outputReceived = Signal(int, str)
    progressChanged = Signal(int, object)
    variantFinished = Signal(object)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, benchmark: PlannedVideo2XBenchmark, variant_indices: tuple[int, ...] | None = None) -> None:
        super().__init__()
        self.benchmark = benchmark
        self.variant_indices = variant_indices or tuple(range(len(benchmark.variants)))
        self.cancellation_token = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            runner = SubprocessJobRunner(progress_parser=_parse_preview_progress_line)
            for index in self.variant_indices:
                if self.cancellation_token.is_cancelled:
                    break
                planned_variant = self.benchmark.variants[index]
                self.variantStarted.emit(index, planned_variant.variant.label)
                job = planned_variant.preview.job
                job.output_path.parent.mkdir(parents=True, exist_ok=True)
                stage_results = []
                variant_error: str | None = None
                for stage in job.stages:
                    if self.cancellation_token.is_cancelled:
                        break
                    self.stageStarted.emit(index, stage.label, _stage_display(stage))
                    result = runner.run_stage(
                        stage,
                        cancellation_token=self.cancellation_token,
                        on_output=lambda line, variant_index=index: self._handle_output(variant_index, line),
                        on_progress=lambda progress, variant_index=index: self.progressChanged.emit(variant_index, progress),
                    )
                    stage_results.append(result)
                    if not result.succeeded:
                        exit_code = result.exit_code
                        variant_error = "cancelled" if result.cancelled else f"{stage.label} failed with exit {exit_code}"
                        break
                run_result = JobRunResult(
                    stages=tuple(stage_results),
                    cancelled=self.cancellation_token.is_cancelled,
                )
                output_path = successful_output_path(run_result, job.output_path)
                self.variantFinished.emit(
                    BenchmarkVariantRun(
                        index=index,
                        output_path=output_path,
                        result=run_result,
                        error=variant_error,
                    )
                )
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    @Slot()
    def cancel(self) -> None:
        self.cancellation_token.cancel()

    def _handle_output(self, variant_index: int, line: ProcessLogLine) -> None:
        self.outputReceived.emit(variant_index, f"{line.stream}: {line.text}")
