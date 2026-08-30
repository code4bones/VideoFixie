"""Domain models independent from Qt and subprocess execution."""

from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import JobProgress, PreviewRange, ProcessingJob, ProcessingStage, TestSegment, TestSegmentKind
from videofixie.domain.media import AudioStreamInfo, MediaInfo, VideoStreamInfo
from videofixie.domain.profiles import ProcessingProfile, bundled_profiles

__all__ = [
    "AudioStreamInfo",
    "BackendCapabilities",
    "GpuDevice",
    "JobProgress",
    "MediaInfo",
    "PlannedCommand",
    "PreviewRange",
    "ProcessingJob",
    "ProcessingProfile",
    "ProcessingStage",
    "ProcessorCapability",
    "TestSegment",
    "TestSegmentKind",
    "VideoStreamInfo",
    "bundled_profiles",
]
