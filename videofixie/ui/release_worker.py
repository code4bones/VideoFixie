from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from videofixie.domain.release_presets import ReleasePreset
from videofixie.jobs.runner import CancellationToken, JobRunResult, ProcessLogLine, SubprocessJobRunner
from videofixie.jobs.runtime_errors import apply_backend_runtime_error
from videofixie.services.app import PlannedRelease
from videofixie.services.run_logs import RunLogFile, create_run_directory
from videofixie.ui.preview_worker import _job_status, _parse_preview_progress_line, _stage_display


class ReleaseWorker(QObject):
    stageStarted = Signal(str, str)
    outputReceived = Signal(str)
    progressChanged = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, release: PlannedRelease, run_logs_root: Path | None = None) -> None:
        super().__init__()
        self.release = release
        self.run_logs_root = run_logs_root
        self.cancellation_token = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            job = self.release.job
            job.output_path.parent.mkdir(parents=True, exist_ok=True)
            run_log = None
            if self.run_logs_root is not None:
                run_dir = create_run_directory(self.run_logs_root, "release")
                run_log = RunLogFile.create(
                    run_dir,
                    "release",
                    "VideoFixie release run",
                    _release_metadata(self.release.release_preset, self.release),
                )
                self.outputReceived.emit(f"run_log: {run_log.path}")

            runner = SubprocessJobRunner(progress_parser=_parse_preview_progress_line)
            results = []
            for stage in job.stages:
                if self.cancellation_token.is_cancelled:
                    break
                if run_log is not None:
                    run_log.append_stage_start(stage)
                self.stageStarted.emit(stage.label, _stage_display(stage))
                result = runner.run_stage(
                    stage,
                    cancellation_token=self.cancellation_token,
                    on_output=lambda line: self._handle_logged_output(run_log, line),
                    on_progress=lambda progress: self.progressChanged.emit(progress),
                )
                result = apply_backend_runtime_error(stage, result)
                if run_log is not None:
                    run_log.append_stage_result(stage, result, include_output=False)
                results.append(result)
                if not result.succeeded:
                    break

            job_result = JobRunResult(stages=tuple(results), cancelled=self.cancellation_token.is_cancelled)
            if run_log is not None:
                details = None
                if results and results[-1].runtime_error:
                    details = results[-1].runtime_error
                run_log.append_status(_job_status(job_result), details)
            self.finished.emit(job_result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    @Slot()
    def cancel(self) -> None:
        self.cancellation_token.cancel()

    def _handle_logged_output(self, log: RunLogFile | None, line: ProcessLogLine) -> None:
        if log is not None:
            log.append_process_line(line.stream, line.text)
        self.outputReceived.emit(f"{line.stream}: {line.text}")


def _release_metadata(release_preset: ReleasePreset, release: PlannedRelease) -> dict[str, str]:
    return {
        "source": str(release.job.source_path),
        "output": str(release.job.output_path),
        "profile": release.profile.slug,
        "release_preset": release_preset.slug,
        "output_preset": release.output_preset.slug,
        "container": release_preset.container,
        "audio_policy": release_preset.audio_policy,
        "subtitle_policy": release_preset.subtitle_policy,
        "metadata_policy": release_preset.metadata_policy,
    }
