from __future__ import annotations

from pathlib import Path
from shlex import quote

from PySide6.QtCore import QObject, Signal, Slot

from videofixie.backends.vapoursynth import parse_progress_line as parse_vapoursynth_progress_line
from videofixie.backends.video2x import parse_progress_line as parse_video2x_progress_line
from videofixie.domain.jobs import JobProgress, ProcessingJob, ProcessingStage
from videofixie.jobs.runner import CancellationToken, JobRunResult, ProcessLogLine, SubprocessJobRunner
from videofixie.services.run_logs import RunLogFile, create_run_directory


class PreviewWorker(QObject):
    stageStarted = Signal(str, str)
    outputReceived = Signal(str)
    progressChanged = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, job: ProcessingJob, run_logs_root: Path | None = None) -> None:
        super().__init__()
        self.job = job
        self.run_logs_root = run_logs_root
        self.cancellation_token = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            self.job.output_path.parent.mkdir(parents=True, exist_ok=True)
            run_log = None
            if self.run_logs_root is not None:
                run_dir = create_run_directory(self.run_logs_root, "preview")
                run_log = RunLogFile.create(
                    run_dir,
                    "preview",
                    "VideoFixie preview run",
                    {
                        "source": str(self.job.source_path),
                        "output": str(self.job.output_path),
                        "profile": self.job.profile.slug,
                        "output_preset": self.job.output_preset.slug,
                    },
                )
                self.outputReceived.emit(f"run_log: {run_log.path}")
            runner = SubprocessJobRunner(progress_parser=_parse_preview_progress_line)
            results = []
            for stage in self.job.stages:
                if self.cancellation_token.is_cancelled:
                    break
                self.stageStarted.emit(stage.label, _stage_display(stage))
                result = runner.run_stage(
                    stage,
                    cancellation_token=self.cancellation_token,
                    on_output=self._handle_output,
                    on_progress=self._handle_progress,
                )
                if run_log is not None:
                    run_log.append_stage_result(stage, result)
                results.append(result)
                if not result.succeeded:
                    break
            job_result = JobRunResult(stages=tuple(results), cancelled=self.cancellation_token.is_cancelled)
            if run_log is not None:
                run_log.append_status(_job_status(job_result))
            self.finished.emit(job_result)
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


def _parse_preview_progress_line(line: str) -> JobProgress | None:
    return parse_video2x_progress_line(line) or parse_vapoursynth_progress_line(line)


def _stage_display(stage: ProcessingStage) -> str:
    command = stage.command.display()
    if stage.cwd is None:
        return command
    return f"cd {quote(str(stage.cwd))} && {command}"


def _job_status(result: JobRunResult) -> str:
    if result.succeeded:
        return "succeeded"
    if result.cancelled:
        return "cancelled"
    return "failed"
