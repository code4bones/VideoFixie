from __future__ import annotations

from pathlib import Path

from videofixie.backends.ffmpeg import FFmpegAdapter
from videofixie.backends.video2x import Video2XAdapter
from videofixie.domain.backends import VIDEO2X_BACKEND_SLUG
from videofixie.domain.capabilities import BackendCapabilities
from videofixie.domain.jobs import PreviewRange, ProcessingJob, ProcessingStage, TestSegment
from videofixie.domain.output_presets import OutputPreset, preview_output_preset
from videofixie.domain.profiles import ProcessingProfile


def build_preview_job(
    source_path: str | Path,
    work_dir: str | Path,
    profile: ProcessingProfile,
    preview_range: PreviewRange,
    device_index: int,
    ffmpeg: FFmpegAdapter,
    video2x: Video2XAdapter,
    capabilities: BackendCapabilities | None = None,
    output_preset: OutputPreset | None = None,
    backend_slug: str = VIDEO2X_BACKEND_SLUG,
) -> ProcessingJob:
    return build_test_segment_job(
        source_path=source_path,
        work_dir=work_dir,
        profile=profile,
        segment=TestSegment(
            label="Preview",
            start_seconds=preview_range.start_seconds,
            end_seconds=preview_range.start_seconds + preview_range.duration_seconds,
        ),
        device_index=device_index,
        ffmpeg=ffmpeg,
        video2x=video2x,
        capabilities=capabilities,
        output_preset=output_preset,
        backend_slug=backend_slug,
    )


def build_test_segment_job(
    source_path: str | Path,
    work_dir: str | Path,
    profile: ProcessingProfile,
    segment: TestSegment,
    device_index: int,
    ffmpeg: FFmpegAdapter,
    video2x: Video2XAdapter,
    capabilities: BackendCapabilities | None = None,
    output_preset: OutputPreset | None = None,
    backend_slug: str = VIDEO2X_BACKEND_SLUG,
) -> ProcessingJob:
    validate_profile_backend_compatibility(profile, backend_slug)
    source = Path(source_path)
    work = Path(work_dir)
    selected_output_preset = output_preset or preview_output_preset()
    segment_slug = _slugify(segment.label)
    preview_source = work / f"{source.stem}.{segment_slug}.preview-source.mp4"
    preview_output = work / f"{source.stem}.{segment_slug}.{profile.slug}.{selected_output_preset.slug}.preview.mp4"

    cut_command = ffmpeg.build_preview_cut_command(
        source_path=source,
        output_path=preview_source,
        start_seconds=segment.start_seconds,
        duration_seconds=segment.duration_seconds,
    )
    upscale_command = video2x.build_upscale_command(
        source_path=preview_source,
        output_path=preview_output,
        profile=profile,
        output_preset=selected_output_preset,
        device_index=device_index,
        capabilities=capabilities,
    )

    return ProcessingJob(
        source_path=source,
        output_path=preview_output,
        profile=profile,
        stages=(
            ProcessingStage(label=cut_command.label, command=cut_command),
            ProcessingStage(label=upscale_command.label, command=upscale_command),
        ),
        output_preset=selected_output_preset,
    )


def validate_profile_backend_compatibility(profile: ProcessingProfile, backend_slug: str) -> None:
    if not profile.supports_backend(backend_slug):
        supported = ", ".join(profile.compatible_backend_slugs) or "none"
        raise ValueError(f"Profile {profile.slug} is not compatible with backend {backend_slug}; supported: {supported}")


def _slugify(value: str) -> str:
    chars = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-") or "segment"
