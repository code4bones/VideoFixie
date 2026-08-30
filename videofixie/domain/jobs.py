from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.output_presets import OutputPreset, preview_output_preset
from videofixie.domain.profiles import ProcessingProfile


@dataclass(frozen=True)
class PreviewRange:
    start_seconds: float
    duration_seconds: float = 15.0

    def __post_init__(self) -> None:
        if self.start_seconds < 0:
            raise ValueError("Preview start must be non-negative")
        if self.duration_seconds <= 0:
            raise ValueError("Preview duration must be positive")


class TestSegmentKind(StrEnum):
    FACE = "FACE"
    MOTION = "MOTION"
    DETAIL = "DETAIL"
    DARK = "DARK"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class TestSegment:
    label: str
    start_seconds: float
    end_seconds: float
    kind: TestSegmentKind = TestSegmentKind.CUSTOM

    def __post_init__(self) -> None:
        if self.start_seconds < 0:
            raise ValueError("Test segment start must be non-negative")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Test segment end must be greater than start")
        if not self.label.strip():
            raise ValueError("Test segment label must not be empty")

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds

    def as_preview_range(self) -> PreviewRange:
        return PreviewRange(
            start_seconds=self.start_seconds,
            duration_seconds=self.duration_seconds,
        )


@dataclass(frozen=True)
class GeneratedFile:
    path: Path
    content: str
    description: str = ""


@dataclass(frozen=True)
class ProcessingStage:
    label: str
    command: PlannedCommand
    generated_files: tuple[GeneratedFile, ...] = ()
    cwd: Path | None = None
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ProcessingJob:
    source_path: Path
    output_path: Path
    profile: ProcessingProfile
    stages: tuple[ProcessingStage, ...]
    output_preset: OutputPreset = field(default_factory=preview_output_preset)


@dataclass(frozen=True)
class JobProgress:
    current_frame: int | None = None
    total_frames: int | None = None
    percent: float | None = None
    fps: float | None = None
    elapsed: str | None = None
    remaining: str | None = None
