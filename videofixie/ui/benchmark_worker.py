from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from videofixie.jobs.runner import CancellationToken, JobRunResult, ProcessLogLine, SubprocessJobRunner
from videofixie.services.app import PlannedVideo2XBenchmark
from videofixie.services.run_logs import RunLogFile, create_run_directory
from videofixie.ui.preview_worker import _parse_preview_progress_line, _stage_display, successful_output_path


@dataclass(frozen=True)
class BenchmarkVariantRun:
    index: int
    output_path: Path | None
    result: JobRunResult
    error: str | None = None
    log_path: Path | None = None


class BenchmarkWorker(QObject):
    variantStarted = Signal(int, str)
    stageStarted = Signal(int, str, str)
    outputReceived = Signal(int, str)
    progressChanged = Signal(int, object)
    variantFinished = Signal(object)
    finished = Signal()
    failed = Signal(str)

    def __init__(
        self,
        benchmark: PlannedVideo2XBenchmark,
        variant_indices: tuple[int, ...] | None = None,
        max_parallel_jobs: int = 1,
        run_logs_root: Path | None = None,
    ) -> None:
        super().__init__()
        self.benchmark = benchmark
        self.variant_indices = tuple(range(len(benchmark.variants))) if variant_indices is None else variant_indices
        self.max_parallel_jobs = min(max(1, max_parallel_jobs), 3)
        self.run_logs_root = run_logs_root
        self.run_dir: Path | None = None
        self.cancellation_token = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            runner = SubprocessJobRunner(progress_parser=_parse_preview_progress_line)
            if self.run_logs_root is not None:
                self.run_dir = create_run_directory(self.run_logs_root, "variants")
                self.outputReceived.emit(-1, f"run_log_dir: {self.run_dir}")
            completed_indices: set[int] = set()
            if len(self.variant_indices) > 1 and self.variant_indices:
                first_variant = self.benchmark.variants[self.variant_indices[0]]
                shared_stage = first_variant.preview.job.stages[0]
                shared_log = self._create_run_log(
                    "shared-source",
                    "VideoFixie benchmark shared source",
                    {
                        "source": str(first_variant.preview.job.source_path),
                        "segment": _segment_text(self.benchmark),
                    },
                )
                if shared_log is not None:
                    self.outputReceived.emit(-1, f"run_log: {shared_log.path}")
                self.stageStarted.emit(-1, "Prepare benchmark source", _stage_display(shared_stage))
                result = runner.run_stage(
                    shared_stage,
                    cancellation_token=self.cancellation_token,
                    on_output=lambda line: self._handle_output(-1, line),
                    on_progress=lambda progress: self.progressChanged.emit(-1, progress),
                )
                if shared_log is not None:
                    shared_log.append_stage_result(shared_stage, result)
                if not result.succeeded:
                    run_result = JobRunResult(stages=(result,), cancelled=self.cancellation_token.is_cancelled)
                    error = "cancelled" if result.cancelled else f"{shared_stage.label} failed with exit {result.exit_code}"
                    if shared_log is not None:
                        shared_log.append_status("cancelled" if result.cancelled else "failed", error)
                    for index in self.variant_indices:
                        self.variantFinished.emit(
                            BenchmarkVariantRun(
                                index=index,
                                output_path=None,
                                result=run_result,
                                error=error,
                                log_path=shared_log.path if shared_log is not None else None,
                            )
                        )
                        completed_indices.add(index)
                    self.finished.emit()
                    return
                if shared_log is not None:
                    shared_log.append_status("succeeded")

            skip_shared_cut = len(self.variant_indices) > 1
            if self.max_parallel_jobs <= 1 or len(self.variant_indices) <= 1:
                for index in self.variant_indices:
                    if self.cancellation_token.is_cancelled:
                        break
                    run = self._run_variant(index, skip_shared_cut)
                    self.variantFinished.emit(run)
                    completed_indices.add(index)
            else:
                executor = ThreadPoolExecutor(max_workers=min(self.max_parallel_jobs, len(self.variant_indices)))
                futures = {
                    executor.submit(self._run_variant, index, skip_shared_cut): index
                    for index in self.variant_indices
                }
                try:
                    for future in as_completed(futures):
                        index = futures[future]
                        if future.cancelled():
                            continue
                        run = future.result()
                        self.variantFinished.emit(run)
                        completed_indices.add(index)
                        if self.cancellation_token.is_cancelled:
                            for pending in futures:
                                if not pending.done():
                                    pending.cancel()
                            break
                finally:
                    executor.shutdown(wait=True, cancel_futures=True)
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

    def _run_variant(self, index: int, skip_shared_cut: bool) -> BenchmarkVariantRun:
        if self.cancellation_token.is_cancelled:
            return BenchmarkVariantRun(
                index=index,
                output_path=None,
                result=JobRunResult(cancelled=True),
                error="cancelled",
            )

        planned_variant = self.benchmark.variants[index]
        self.variantStarted.emit(index, planned_variant.variant.label)
        variant_log = self._create_run_log(
            f"variant-{index + 1:02d}-{planned_variant.variant.label}",
            "VideoFixie benchmark variant",
            {
                "variant_index": str(index),
                "variant_label": planned_variant.variant.label,
                "parameters": planned_variant.variant.parameters,
                "source": str(planned_variant.preview.job.source_path),
                "output": str(planned_variant.preview.job.output_path),
                "profile": planned_variant.variant.profile.slug,
                "segment": _segment_text(self.benchmark),
            },
        )
        if variant_log is not None:
            self.outputReceived.emit(index, f"run_log: {variant_log.path}")
        job = planned_variant.preview.job
        job.output_path.parent.mkdir(parents=True, exist_ok=True)
        runner = SubprocessJobRunner(progress_parser=_parse_preview_progress_line)
        stage_results = []
        variant_error: str | None = None
        stages = job.stages[1:] if skip_shared_cut else job.stages
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
            if variant_log is not None:
                variant_log.append_stage_result(stage, result)
            stage_results.append(result)
            if not result.succeeded:
                exit_code = result.exit_code
                variant_error = "cancelled" if result.cancelled else f"{stage.label} failed with exit {exit_code}"
                break
        run_result = JobRunResult(
            stages=tuple(stage_results),
            cancelled=self.cancellation_token.is_cancelled,
        )
        if variant_log is not None:
            variant_log.append_status(_job_status(run_result), variant_error)
        return BenchmarkVariantRun(
            index=index,
            output_path=successful_output_path(run_result, job.output_path),
            result=run_result,
            error=variant_error,
            log_path=variant_log.path if variant_log is not None else None,
        )

    def _handle_output(self, variant_index: int, line: ProcessLogLine) -> None:
        self.outputReceived.emit(variant_index, f"{line.stream}: {line.text}")

    def _create_run_log(self, name: str, title: str, metadata: dict[str, str]) -> RunLogFile | None:
        if self.run_dir is None:
            return None
        return RunLogFile.create(self.run_dir, name, title, metadata)


def _segment_text(benchmark: PlannedVideo2XBenchmark) -> str:
    return (
        f"{benchmark.segment.label} "
        f"{benchmark.segment.start_seconds:.3f}-{benchmark.segment.end_seconds:.3f}s"
    )


def _job_status(result: JobRunResult) -> str:
    if result.succeeded:
        return "succeeded"
    if result.cancelled:
        return "cancelled"
    return "failed"
