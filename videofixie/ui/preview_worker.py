from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from videofixie.backends.video2x import parse_progress_line
from videofixie.domain.jobs import JobProgress, ProcessingJob
from videofixie.jobs.runner import CancellationToken, JobRunResult, ProcessLogLine, SubprocessJobRunner


class PreviewWorker(QObject):
    stageStarted = Signal(str, str)
    outputReceived = Signal(str)
    progressChanged = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, job: ProcessingJob) -> None:
        super().__init__()
        self.job = job
        self.cancellation_token = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            self.job.output_path.parent.mkdir(parents=True, exist_ok=True)
            runner = SubprocessJobRunner(progress_parser=parse_progress_line)
            results = []
            for stage in self.job.stages:
                if self.cancellation_token.is_cancelled:
                    break
                self.stageStarted.emit(stage.label, stage.command.display())
                result = runner.run_command(
                    stage.command,
                    cancellation_token=self.cancellation_token,
                    on_output=self._handle_output,
                    on_progress=self._handle_progress,
                )
                results.append(result)
                if not result.succeeded:
                    break
            self.finished.emit(JobRunResult(stages=tuple(results), cancelled=self.cancellation_token.is_cancelled))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    @Slot()
    def cancel(self) -> None:
        self.cancellation_token.cancel()

    def _handle_output(self, line: ProcessLogLine) -> None:
        self.outputReceived.emit(f"{line.stream}: {line.text}")

    def _handle_progress(self, progress: JobProgress) -> None:
        self.progressChanged.emit(progress)


def successful_output_path(result: JobRunResult, expected_path: Path) -> Path | None:
    if result.succeeded and expected_path.exists():
        return expected_path
    return None
