from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from videofixie.backends.ffmpeg import FFmpegAdapter
from videofixie.backends.video2x import Video2XAdapter
from videofixie.domain.jobs import ProcessingJob, TestSegment
from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import OutputPreset, bundled_output_presets, preview_output_preset
from videofixie.domain.profiles import ProcessingProfile, bundled_profiles
from videofixie.services.environment import MachineEnvironment, discover_environment
from videofixie.services.history import PreviewResult, SavedCut, VideoFixieHistory
from videofixie.services.planner import build_test_segment_job


@dataclass(frozen=True)
class PlannedPreview:
    media: MediaInfo
    environment: MachineEnvironment
    profile: ProcessingProfile
    segment: TestSegment
    job: ProcessingJob
    output_preset: OutputPreset = field(default_factory=preview_output_preset)


class VideoFixieService:
    def __init__(self, project_root: str | Path = ".", history: VideoFixieHistory | None = None) -> None:
        self.project_root = Path(project_root)
        self._history = history

    @property
    def history(self) -> VideoFixieHistory:
        if self._history is None:
            self._history = VideoFixieHistory()
        return self._history

    def discover_environment(self) -> MachineEnvironment:
        return discover_environment(self.project_root)

    def analyze_source(self, source_path: str | Path) -> MediaInfo:
        return FFmpegAdapter().probe(source_path)

    def profiles(self) -> tuple[ProcessingProfile, ...]:
        return bundled_profiles()

    def output_presets(self) -> tuple[OutputPreset, ...]:
        return bundled_output_presets()

    def save_source_segment(
        self,
        source_path: str | Path,
        segment: TestSegment,
        profile_slug: str | None = None,
        output_preset_slug: str | None = None,
    ) -> None:
        self.history.save_segment(source_path, segment, profile_slug, output_preset_slug)

    def load_source_segment(self, source_path: str | Path) -> TestSegment | None:
        return self.history.load_segment(source_path)

    def load_source_cut(self, source_path: str | Path) -> SavedCut | None:
        return self.history.load_cut(source_path)

    def record_preview_result(
        self,
        source_path: str | Path,
        output_path: str | Path,
        profile: ProcessingProfile,
        segment: TestSegment,
        output_preset: OutputPreset | None = None,
    ) -> PreviewResult:
        selected_output_preset = output_preset or preview_output_preset()
        self.save_source_segment(source_path, segment, profile.slug, selected_output_preset.slug)
        return self.history.add_preview_result(source_path, output_path, profile, segment, selected_output_preset)

    def preview_results_for_source(self, source_path: str | Path) -> tuple[PreviewResult, ...]:
        return self.history.preview_results(source_path)

    def plan_preview(
        self,
        source_path: str | Path,
        work_dir: str | Path,
        profile: ProcessingProfile,
        segment: TestSegment,
        device_index: int | None = None,
        output_preset: OutputPreset | None = None,
    ) -> PlannedPreview:
        environment = self.discover_environment()
        if not environment.ffmpeg.available or environment.ffmpeg.path is None:
            raise RuntimeError(f"ffmpeg is unavailable: {environment.ffmpeg.error}")
        if not environment.ffprobe.available or environment.ffprobe.path is None:
            raise RuntimeError(f"ffprobe is unavailable: {environment.ffprobe.error}")
        if not environment.video2x.available or environment.video2x.path is None:
            raise RuntimeError(f"Video2X is unavailable: {environment.video2x.error}")

        selected_device = device_index
        if selected_device is None:
            if environment.preferred_gpu is None:
                raise RuntimeError("No Video2X Vulkan device discovered")
            selected_device = environment.preferred_gpu.index

        media = self.analyze_source(source_path)
        selected_output_preset = output_preset or preview_output_preset()
        job = build_test_segment_job(
            source_path=source_path,
            work_dir=work_dir,
            profile=profile,
            segment=segment,
            device_index=selected_device,
            ffmpeg=FFmpegAdapter(ffmpeg_path=environment.ffmpeg.path, ffprobe_path=environment.ffprobe.path),
            video2x=Video2XAdapter(environment.video2x.path),
            capabilities=environment.video2x_capabilities,
            output_preset=selected_output_preset,
        )

        return PlannedPreview(
            media=media,
            environment=environment,
            profile=profile,
            output_preset=selected_output_preset,
            segment=segment,
            job=job,
        )

    def plan_preview_with_context(
        self,
        source_path: str | Path,
        work_dir: str | Path,
        profile: ProcessingProfile,
        segment: TestSegment,
        media: MediaInfo,
        environment: MachineEnvironment,
        device_index: int | None = None,
        output_preset: OutputPreset | None = None,
    ) -> PlannedPreview:
        if not environment.ffmpeg.available or environment.ffmpeg.path is None:
            raise RuntimeError(f"ffmpeg is unavailable: {environment.ffmpeg.error}")
        if not environment.ffprobe.available or environment.ffprobe.path is None:
            raise RuntimeError(f"ffprobe is unavailable: {environment.ffprobe.error}")
        if not environment.video2x.available or environment.video2x.path is None:
            raise RuntimeError(f"Video2X is unavailable: {environment.video2x.error}")

        selected_device = device_index
        if selected_device is None:
            if environment.preferred_gpu is None:
                raise RuntimeError("No Video2X Vulkan device discovered")
            selected_device = environment.preferred_gpu.index

        selected_output_preset = output_preset or preview_output_preset()
        job = build_test_segment_job(
            source_path=source_path,
            work_dir=work_dir,
            profile=profile,
            segment=segment,
            device_index=selected_device,
            ffmpeg=FFmpegAdapter(ffmpeg_path=environment.ffmpeg.path, ffprobe_path=environment.ffprobe.path),
            video2x=Video2XAdapter(environment.video2x.path),
            capabilities=environment.video2x_capabilities,
            output_preset=selected_output_preset,
        )

        return PlannedPreview(
            media=media,
            environment=environment,
            profile=profile,
            output_preset=selected_output_preset,
            segment=segment,
            job=job,
        )
