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
        self.variant_indices = tuple(range(len(benchmark.variants))) if variant_indices is None else variant_indices
        self.cancellation_token = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            runner = SubprocessJobRunner(progress_parser=_parse_preview_progress_line)
            completed_indices: set[int] = set()
            if len(self.variant_indices) > 1 and self.variant_indices:
                first_variant = self.benchmark.variants[self.variant_indices[0]]
                shared_stage = first_variant.preview.job.stages[0]
                self.stageStarted.emit(-1, "Prepare benchmark source", _stage_display(shared_stage))
                result = runner.run_stage(
                    shared_stage,
                    cancellation_token=self.cancellation_token,
                    on_output=lambda line: self._handle_output(-1, line),
                    on_progress=lambda progress: self.progressChanged.emit(-1, progress),
                )
                if not result.succeeded:
                    run_result = JobRunResult(stages=(result,), cancelled=self.cancellation_token.is_cancelled)
                    error = "cancelled" if result.cancelled else f"{shared_stage.label} failed with exit {result.exit_code}"
                    for index in self.variant_indices:
                        self.variantFinished.emit(
                            BenchmarkVariantRun(
                                index=index,
                                output_path=None,
                                result=run_result,
                                error=error,
                            )
                        )
                        completed_indices.add(index)
                    self.finished.emit()
                    return

            for index in self.variant_indices:
                if self.cancellation_token.is_cancelled:
                    break
                planned_variant = self.benchmark.variants[index]
                self.variantStarted.emit(index, planned_variant.variant.label)
                job = planned_variant.preview.job
                job.output_path.parent.mkdir(parents=True, exist_ok=True)
                stage_results = []
                variant_error: str | None = None
                stages = job.stages[1:] if len(self.variant_indices) > 1 else job.stages
                for stage in stages:
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
                completed_indices.add(index)
            if self.cancellation_token.is_cancelled:
                run_result = JobRunResult(cancelled=True)
                for index in self.variant_indices:
                    if index not in completed_indices:
                        self.variantFinished.emit(
                            BenchmarkVariantRun(
                                index=index,
                                output_path=None,
                                result=run_result,
                                error="cancelled",
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
