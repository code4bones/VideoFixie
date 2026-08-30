from __future__ import annotations

from dataclasses import dataclass

from videofixie.domain.profiles import ProcessingProfile


@dataclass(frozen=True)
class Video2XBenchmarkVariant:
    profile: ProcessingProfile
    label: str
    parameters: str

