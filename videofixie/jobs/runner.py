from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import JobProgress, ProcessingJob

ProgressParser = Callable[[str], JobProgress | None]
OutputCallback = Callable[["ProcessLogLine"], None]
ProgressCallback = Callable[[JobProgress], None]


@dataclass(frozen=True)
class ProcessLogLine:
    stream: str
    text: str


@dataclass(frozen=True)
class StageRunResult:
    label: str
    command: PlannedCommand
    exit_code: int
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
    progress: tuple[JobProgress, ...] = ()
    cancelled: bool = False
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.cancelled


@dataclass(frozen=True)
class JobRunResult:
    stages: tuple[StageRunResult, ...] = field(default_factory=tuple)
    cancelled: bool = False

    @property
    def succeeded(self) -> bool:
        return bool(self.stages) and all(stage.succeeded for stage in self.stages)


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


class SubprocessJobRunner:
    def __init__(self, progress_parser: ProgressParser | None = None, terminate_grace_seconds: float = 2.0) -> None:
        self.progress_parser = progress_parser
        self.terminate_grace_seconds = terminate_grace_seconds

    def run_job(
        self,
        job: ProcessingJob,
        cancellation_token: CancellationToken | None = None,
        on_output: OutputCallback | None = None,
        on_progress: ProgressCallback | None = None,
        cwd: str | Path | None = None,
    ) -> JobRunResult:
        results: list[StageRunResult] = []
        token = cancellation_token or CancellationToken()

        for stage in job.stages:
            result = self.run_command(
                stage.command,
                cancellation_token=token,
                on_output=on_output,
                on_progress=on_progress,
                cwd=cwd,
            )
            results.append(result)
            if not result.succeeded:
                return JobRunResult(stages=tuple(results), cancelled=result.cancelled)

        return JobRunResult(stages=tuple(results), cancelled=token.is_cancelled)

    def run_command(
        self,
        command: PlannedCommand,
        cancellation_token: CancellationToken | None = None,
        on_output: OutputCallback | None = None,
        on_progress: ProgressCallback | None = None,
        cwd: str | Path | None = None,
    ) -> StageRunResult:
        token = cancellation_token or CancellationToken()
        start_time = time.monotonic()
        stdout: list[str] = []
        stderr: list[str] = []
        progress_events: list[JobProgress] = []
        output_queue: queue.Queue[ProcessLogLine | None] = queue.Queue()

        process = subprocess.Popen(
            command.argv(),
            cwd=str(cwd) if cwd is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        readers = (
            threading.Thread(target=_read_stream, args=(process.stdout, "stdout", output_queue), daemon=True),
            threading.Thread(target=_read_stream, args=(process.stderr, "stderr", output_queue), daemon=True),
        )
        for reader in readers:
            reader.start()

        open_streams = len(readers)
        cancelled = False

        while open_streams:
            if token.is_cancelled and process.poll() is None:
                cancelled = True
                _terminate_process(process, self.terminate_grace_seconds)

            try:
                item = output_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if item is None:
                open_streams -= 1
                continue

            if item.stream == "stdout":
                stdout.append(item.text)
            else:
                stderr.append(item.text)

            if on_output is not None:
                on_output(item)

            progress = self.progress_parser(item.text) if self.progress_parser is not None else None
            if progress is not None:
                progress_events.append(progress)
                if on_progress is not None:
                    on_progress(progress)

        for reader in readers:
            reader.join(timeout=0.1)

        exit_code = process.wait()
        duration = time.monotonic() - start_time

        return StageRunResult(
            label=command.label,
            command=command,
            exit_code=exit_code,
            stdout=tuple(stdout),
            stderr=tuple(stderr),
            progress=tuple(progress_events),
            cancelled=cancelled,
            duration_seconds=duration,
        )


def _read_stream(stream, stream_name: str, output_queue: queue.Queue[ProcessLogLine | None]) -> None:
    try:
        if stream is None:
            return
        with stream:
            for line in stream:
                output_queue.put(ProcessLogLine(stream=stream_name, text=line.rstrip("\n")))
    finally:
        output_queue.put(None)


def _terminate_process(process: subprocess.Popen[str], grace_seconds: float) -> None:
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
