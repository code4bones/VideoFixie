from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from videofixie.domain.jobs import ProcessingStage
from videofixie.jobs.runner import StageRunResult


def create_run_directory(root: str | Path, prefix: str) -> Path:
    run_id = f"{_slug(prefix)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{uuid4().hex[:8]}"
    path = Path(root).expanduser() / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path


@dataclass
class RunLogFile:
    path: Path
    _lock: threading.Lock

    @classmethod
    def create(cls, run_dir: str | Path, name: str, title: str, metadata: dict[str, str] | None = None) -> "RunLogFile":
        path = Path(run_dir) / f"{_slug(name)}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        log = cls(path=path, _lock=threading.Lock())
        lines = [
            title,
            f"created_at: {datetime.now().isoformat(timespec='seconds')}",
            f"path: {path}",
        ]
        for key, value in (metadata or {}).items():
            lines.append(f"{key}: {value}")
        log.append_lines((*lines, ""))
        return log

    def append_lines(self, lines: tuple[str, ...]) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line)
                    handle.write("\n")

    def append_stage_start(self, stage: ProcessingStage) -> None:
        lines = [
            "----- stage -----",
            f"label: {stage.label}",
            "status: running",
            f"cwd: {stage.cwd or ''}",
            "command:",
            stage.command.display(),
        ]
        for generated_file in stage.generated_files:
            description = generated_file.description or "Generated file"
            lines.extend(
                [
                    "generated_file:",
                    f"  description: {description}",
                    f"  path: {generated_file.path}",
                ]
            )
        lines.append("")
        self.append_lines(tuple(lines))

    def append_process_line(self, stream: str, text: str) -> None:
        self.append_lines((f"{stream}: {text}",))

    def append_stage_result(self, stage: ProcessingStage, result: StageRunResult, include_output: bool = True) -> None:
        cwd = stage.cwd if stage.cwd is not None else result.cwd
        lines = [
            "----- stage result -----",
            f"label: {stage.label}",
            f"status: {_stage_status(result)}",
            f"exit_code: {result.exit_code}",
            f"cancelled: {result.cancelled}",
            f"duration_seconds: {result.duration_seconds:.3f}",
            f"cwd: {cwd or ''}",
            "command:",
            result.command.display(),
        ]
        if result.runtime_error:
            lines.append(f"runtime_error: {result.runtime_error}")
        for generated_file in stage.generated_files:
            description = generated_file.description or "Generated file"
            lines.extend(
                [
                    "generated_file:",
                    f"  description: {description}",
                    f"  path: {generated_file.path}",
                ]
            )
        if include_output:
            lines.append("stdout:")
            lines.extend(f"  {line}" for line in result.stdout)
            lines.append("stderr:")
            lines.extend(f"  {line}" for line in result.stderr)
        else:
            lines.extend(("stdout: <captured live above>", "stderr: <captured live above>"))
        lines.append("")
        self.append_lines(tuple(lines))

    def append_status(self, status: str, details: str | None = None) -> None:
        lines = ["----- result -----", f"status: {status}"]
        if details:
            lines.append(f"details: {details}")
        lines.append("")
        self.append_lines(tuple(lines))


def _stage_status(result: StageRunResult) -> str:
    if result.succeeded:
        return "succeeded"
    if result.cancelled:
        return "cancelled"
    return "failed"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-")
    return slug or "run"
